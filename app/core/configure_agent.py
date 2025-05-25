import logging
import sys
from typing import Optional
import json
import time
from livekit.agents import JobContext,RunContext
from livekit.agents.llm import function_tool
from livekit.agents.voice import Agent, AgentSession
from app.utils.end_call_tool import end_call
from app.core.ws_manager import ws_manager
from livekit.plugins import silero
from app.utils.agent_builder import build_llm_instance, build_stt_instance, build_tts_instance
from app.utils.query_tool import build_query_tool
from app.utils.mongodb_client import MongoDBClient
from app.utils.configure_nodes import parse_agent_config
from app.utils.transcript_fnc import write_transcript_file

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("agent-runner")

async def generate_function_tools(config, module, agent_id):
    for route in config.get("routes", []):
        tool_name = route["tool_name"]
        next_node = route["next_node"]
        tool_definition = route.get("condition", "")

        def make_tool(next_node_val):
            @function_tool(name=tool_name, description=f"Use this tool if {tool_definition}")
            async def tool_fn(context: RunContext):
                start = time.perf_counter()
                chat_ctx = context.session._chat_ctx
                agent=await create_agent(
                    next_node_val,
                    chat_ctx=chat_ctx,
                    agent_config=context.session._agent_config,
                    agent_id=agent_id
                )
                end = time.perf_counter()
                logger.info(f"Time taken to create agent: {end - start} seconds")
                return agent
            return tool_fn

        if not hasattr(module, tool_name):
            setattr(module, tool_name, make_tool(next_node))

class GenericAgent(Agent):
    def __init__(self, prompt: str, tools: Optional[list] = None, chat_ctx=None, agent_config=None, node_config=None):
        global_prompt = agent_config.global_settings.global_prompt if agent_config.global_settings else ""

        self._agent_config = agent_config
        self._node_config = node_config

        super().__init__(
            instructions=f"{global_prompt}\n{prompt}",
            tools=tools or [],
            chat_ctx=chat_ctx
        )

    async def on_enter(self):
        await self.session.generate_reply()

async def create_agent(node_id: str, chat_ctx=None, agent_config=None, agent_id=None) -> Agent:
    tools = []

    if getattr(agent_config.global_settings, "vector_store_id", None):
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
        prompt =f"Say: {node_config.static_sentence}"

    if node_config.routes:
        module = sys.modules[__name__]
        await generate_function_tools(node_config.dict(), module, agent_id)
        for route in node_config.routes:
            tools.append(getattr(module, route.tool_name))

    # if getattr(node_config, "is_exit_node", False):
    tools.append(end_call)

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
            code_str = codecs.decode(tool_data["function_code"], "unicode_escape")  # 🔥 FIX here
            print("Function code string to exec:\n", code_str)

            exec(code_str, globals(), local_vars)
            fn_ref = local_vars.get("tool_fn")
            logger.info(f"Compiling custom tool for node {node_config.node_id}: {tool_data['tool_name']}")
            
            if fn_ref:
                wrapped_tool = function_tool(
                    fn_ref,
                    name=tool_data["tool_name"],
                    description=tool_data["tool_description"]
                )
                tools.append(wrapped_tool)
                logger.info(f"Custom tool '{tool_data['tool_name']}' compiled successfully for node {node_config.node_id}")
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

async def entrypoint(ctx: JobContext):
    try:
        metadata = json.loads(ctx.job.metadata)
        agent_id = metadata["agent_id"]

        mongo_client = MongoDBClient()
        flow = mongo_client.get_flow_by_id(agent_id)

        if not flow:
            logger.error(f"Agent config not found in MongoDB for ID: {agent_id}")
            return

        api_key = flow.get("global_settings", {}).get("tts", {}).get("api_key")
        if isinstance(api_key, dict):
            private_key = api_key.get("private_key")
            if private_key and "\\n" in private_key:
                api_key["private_key"] = private_key.replace("\\n", "\n")

        agent_config = parse_agent_config(flow)

        if not agent_config.nodes or not agent_config.global_settings:
            logger.error(f"Incomplete agent config for flow execution: {agent_id}")
            return

        logger.info(f"Starting session in room: {ctx.room.name} with agent ID: {agent_id}")
        await ctx.connect()

        llm = build_llm_instance(
            agent_config.global_settings.llm.provider,
            agent_config.global_settings.llm.model,
            agent_config.global_settings.llm.api_key,
            agent_config.global_settings.temperature
        )
        stt = build_stt_instance(
            agent_config.global_settings.stt.provider,
            agent_config.global_settings.stt.model,
            agent_config.global_settings.stt.language,
            agent_config.global_settings.stt.api_key
        )
        tts = build_tts_instance(
            agent_config.global_settings.tts.provider,
            agent_config.global_settings.tts.model,
            agent_config.global_settings.tts.language,
            credentials_info=agent_config.global_settings.tts.api_key
        )

        session = AgentSession(
            stt=stt, 
            llm=llm, 
            tts=tts, 
            # vad=ctx.proc.userdata["vad"]
            vad=silero.VAD.load()
            )
        session._agent_config = agent_config

        ctx.add_shutdown_callback(lambda:write_transcript_file(session, ctx.room.name))

        entry_node = agent_config.entry_node
        if not entry_node:
            logger.error("No entry node found in agent config")
            return

        agent = await create_agent(entry_node, agent_config=agent_config, agent_id=agent_id)
        await session.start(agent=agent, room=ctx.room)

    except Exception as e:
        logger.exception(f"Unexpected error in entrypoint: {e}")

