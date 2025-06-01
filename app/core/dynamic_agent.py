import logging
import sys
from typing import Optional
import time
import asyncio
from livekit.agents import RunContext
from livekit.agents.llm import function_tool
from livekit.agents.voice import Agent
from app.utils.call_control_tools import end_call ,detected_answering_machine, hangup
from app.core.ws_manager import ws_manager
from app.utils.query_tool import build_query_tool
import copy

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
        self._silence_task = None

        super().__init__(
            instructions=f"{global_prompt}\n{prompt}",
            tools=tools or [],
            chat_ctx=chat_ctx
        )

    async def on_enter(self):
        await self.session.generate_reply()
        silnc = self._agent_config.global_settings.timeout_seconds

        if isinstance(silnc, (int, float)) and silnc > 0:
            logger.info(f"Starting silence detection with timeout: {silnc} seconds")

            if self._silence_task and not self._silence_task.done():
                self._silence_task.cancel()
                logger.info("Previous silence detection task cancelled")

            self._silence_task = asyncio.create_task(self._detect_silence(timeout_seconds=silnc))

    async def _detect_silence(self, timeout_seconds: int = 30):
        last_listening_start = None
        warning_given = False

        try:
            while True:
                if getattr(self.session, "ended", False):
                    logger.info("Session ended. Exiting silence detection loop.")
                    break

                current_state = self.session._agent_state

                if current_state == "speaking":
                    last_listening_start = None
                    warning_given = False

                elif current_state == "listening":
                    if last_listening_start is None:
                        last_listening_start = time.time()
                    else:
                        elapsed = time.time() - last_listening_start
                        if elapsed > timeout_seconds:
                            logger.info("Silence timeout reached. Ending call...")
                            try:
                                await self.session.say(
                                    "It seems we've lost connection or you're unavailable. Ending the call now. Take care.",
                                    allow_interruptions=False
                                )
                                await hangup()
                            except Exception as e:
                                logger.error(f"Failed during final hangup: {e}")
                            break

                        elif elapsed > timeout_seconds / 2 and not warning_given:
                            warning_given = True
                            logger.info("Giving silence warning prompt to user")
                            await self.session.say(
                                "Hello? I'm still here. Please respond in the next few seconds or I will have to end the call."
                            )
                            
                            # Check every 0.5s for up to 5 seconds
                            for _ in range(10):
                                await asyncio.sleep(0.5)

                                current_state = self.session._agent_state
                                user_state = self.session._user_state

                                if current_state != "listening" or user_state == "speaking":
                                    logger.info("User responded or LLM resumed after warning. Resetting silence timer.")
                                    last_listening_start = None
                                    warning_given = False
                                    break

                else:
                    last_listening_start = None
                    warning_given = False

                await asyncio.sleep(1)

        except asyncio.CancelledError:
            logger.info("Silence detection task was cancelled")

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
