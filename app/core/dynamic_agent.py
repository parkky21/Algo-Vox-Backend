import logging
import sys
from typing import Optional
import time
from livekit.agents import RunContext
from livekit.agents.llm import function_tool
from livekit.agents.voice import Agent
from app.utils.call_control_tools import end_call ,detected_answering_machine, hangup
from app.core.ws_manager import ws_manager
from app.utils.query_tool import build_query_tool
import copy
from datetime import datetime, timezone
from app.utils.silence_detection import SilenceDetector

now = datetime.now(timezone.utc).strftime("%A, %B %d, %Y at %I:%M %p UTC")
current_time = f"The current date and time is {now}."

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("DynamicAgent")

async def generate_function_tools(config, module, agent_id, agent_config):
    for route in config.get("routes", []):
        tool_name = route["tool_name"]
        next_node = route["next_node"]
        tool_definition = route.get("condition", "")

        frozen_config = copy.deepcopy(agent_config)

        def make_tool(next_node_val, frozen_agent_config):
            @function_tool(name=tool_name, description=f"Use this tool {tool_definition}")
            async def tool_fn(context: RunContext):
                start = time.perf_counter()
                chat_ctx = context.session._chat_ctx
                agent = await create_agent(
                    next_node_val,
                    chat_ctx=chat_ctx,
                    agent_config=frozen_agent_config,
                    agent_id=agent_id
                )
                end = time.perf_counter()
                logger.info(f"Time taken to create agent: {end - start} seconds")
                return agent
            return tool_fn

        if hasattr(module, tool_name):
            delattr(module, tool_name)

        setattr(module, tool_name, make_tool(next_node, frozen_config))

class GenericAgent(Agent):
    def __init__(self, prompt: str, tools: Optional[list] = None, chat_ctx=None, agent_config=None, node_config=None):
        global_prompt = agent_config.global_settings.global_prompt if agent_config.global_settings else ""

        self._agent_config = agent_config
        self._node_config = node_config
        self._silence_detector = None  # Changed from _silence_task to _silence_detector

        super().__init__(
            instructions=f"{global_prompt}\n{prompt}\n{current_time}",
            tools=tools or [],
            chat_ctx=chat_ctx
        )

    def _get_timeout_config(self) -> tuple[Optional[int], int]:
        """Get timeout configuration from agent config."""
        initial_timeout = None
        warning_timeout = 5  # Default 5 seconds for warning
        
        if (self._agent_config and 
            hasattr(self._agent_config, 'global_settings') and 
            self._agent_config.global_settings):
            
            settings = self._agent_config.global_settings
            # Try new config fields first
            initial_timeout = getattr(settings, 'initial_timeout_seconds', None)
            warning_timeout = getattr(settings, 'warning_timeout_seconds', 5)
            
            # For backward compatibility with old config
            if initial_timeout is None:
                old_timeout = getattr(settings, 'timeout_seconds', None)
                if old_timeout:
                    # Split old timeout: use most of it for initial, keep 5s for warning
                    initial_timeout = max(old_timeout - warning_timeout, 5)  # Minimum 5s initial
        
        return initial_timeout, warning_timeout

    async def on_enter(self):
        """Start agent and silence detection."""
        logger.info(self.chat_ctx)
        await self.session.generate_reply()
        
        # Get timeout configuration
        initial_timeout, warning_timeout = self._get_timeout_config()
        if initial_timeout and initial_timeout > 0:
            self._silence_detector = SilenceDetector(self.session, initial_timeout, warning_timeout)
            await self._silence_detector.start()

    async def on_exit(self):
        """Cleanup when agent exits."""
        if self._silence_detector:
            await self._silence_detector.stop()
            self._silence_detector = None

async def create_agent(node_id: str, chat_ctx=None, agent_config=None, agent_id=None) -> Agent:
    tools = []
    if agent_config.global_settings and agent_config.global_settings.vector_store_id:
        try:
            query_tool = build_query_tool(agent_config.global_settings.vector_store_id)
            tools.append(query_tool)
        except Exception as e:
            logger.error(f"Failed to load vector store tool: {e}")

    agent_flow = {node.node_id: node for node in agent_config.nodes}

    if node_id not in agent_flow:
        raise ValueError(f"Node '{node_id}' not found. Available nodes: {list(agent_flow.keys())}")

    node_config = agent_flow[node_id]
    node_type = node_config.type
    if node_config.prompt:
        prompt = node_config.prompt
    elif node_config.static_sentence:
        prompt = f"Say: {node_config.static_sentence}"
    else:
        prompt = ""

    if node_config.routes:
        module = sys.modules[__name__]
        await generate_function_tools(node_config.dict(), module, agent_id, agent_config)
        for route in node_config.routes:
            tools.append(getattr(module, route.tool_name))

    if node_config.is_end_node:
        tools.append(end_call)
        logger.info(f"Added end_call tool to node {node_id}")

    if node_config.detected_answering_machine:
        tools.append(detected_answering_machine)
        logger.info(f"Added detected_answering_machine tool to node {node_id}")

    if agent_id:
        await ws_manager.send_node_update(agent_id, node_id)
        logger.info(f"Node switched to: {node_id}")

    if node_type == "conversation":
        return GenericAgent(
            prompt=prompt,
            tools=tools,
            chat_ctx=chat_ctx,
            agent_config=agent_config,
            node_config=node_config
        )

    elif node_type == "function":
        tool_data = node_config.custom_function
        local_vars = {}
        import codecs

        try:
            code_str = codecs.decode(tool_data.code, "unicode_escape")
            print("Function code string to exec:\n", code_str)

            exec(code_str, globals(), local_vars)
            fn_ref = local_vars.get("tool_fn")
            logger.info(f"Compiling custom tool for node {node_config.node_id}: {tool_data.name}")

            if fn_ref:
                wrapped_tool = function_tool(
                    fn_ref,
                    name=tool_data.name,
                    description=tool_data.description
                )
                tools.append(wrapped_tool)
                logger.info(f"Custom tool '{tool_data.name}' compiled successfully for node {node_config.node_id}")
            else:
                raise ValueError("No 'tool_fn' defined in function_code")

        except Exception as e:
            logger.error(f"Failed to compile custom tool for node {node_config.node_id}: {e}")

        return GenericAgent(
            prompt=prompt,
            tools=tools,
            chat_ctx=chat_ctx,
            agent_config=agent_config,
            node_config=node_config
        )

    elif node_type == "call_transfer":
        async def transfer_call() -> str:
            logger.info(f"Transferring call for agent: {agent_id}")
            return "Your call is being transferred to a human agent. Please stay on the line."

        tools.append(function_tool(transfer_call, name="transfer_call", description="Transfers the call"))

        return GenericAgent(
            prompt="Please wait while we connect you...",
            tools=tools,
            chat_ctx=chat_ctx,
            agent_config=agent_config,
            node_config=node_config
        )

    else:
        raise ValueError(f"Unknown node type: {node_type}")
