import logging
import sys
from typing import Optional
from datetime import datetime
import json
import os
from livekit.agents import Worker
from livekit import api
from pathlib import Path
from livekit.agents import JobContext, WorkerOptions
from livekit.agents.llm import function_tool
from livekit.agents.voice import Agent, AgentSession, RunContext
from livekit.plugins import silero
from app.core.config import get_agent_config 
from app.core.models import AgentConfig
from app.utils.end_call_tool import end_call
from app.core.ws_manager import ws_manager
from app.core.settings import settings
from app.utils.agent_builder import build_llm_instance, build_stt_instance, build_tts_instance
from app.utils.helper import place_order,list_orders
from llama_index.core import StorageContext, load_index_from_storage
from app.api.routes.vector_stores import vector_stores

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("agent-runner")

def build_query_tool(store_id: str):
    from livekit.agents.llm import function_tool

    # Get embed_model from memory if loaded in `vector_stores` dict
    vs_info = vector_stores.get(store_id)
    if not vs_info:
        raise ValueError(f"Vector store {store_id} not found in memory.")

    provider = vs_info["config"].get("provider", "")
    if provider.lower() == "openai":
        os.environ["OPENAI_API_KEY"] = vs_info["config"].get("api_key", "")

    store_path = Path("vector_stores") / store_id
    storage_context = StorageContext.from_defaults(persist_dir=store_path)

    index = load_index_from_storage(storage_context, embed_model=vs_info["embed_model"])
    query_engine = index.as_query_engine(use_async=True)

    @function_tool()
    async def query_info(query: str) -> str:
        """Use this tool to know about a specific topic or information"""
        result = await query_engine.aquery(query)
        return str(result)

    return query_info

async def generate_function_tools(config, module, agent_id):
    for route in config.get("routes", []):
        tool_name = route["tool_name"]
        next_node = route["next_node"]
        tool_definition = route.get("condition", "")

        def make_tool(next_node_val):
            @function_tool(name=tool_name, description=f"Use this tool if {tool_definition}")
            async def tool_fn(context: RunContext):
                chat_ctx = context.session._chat_ctx
                return await create_agent(next_node_val, chat_ctx=chat_ctx, agent_config=context.session._agent_config, agent_id=agent_id)
            return tool_fn

        setattr(module, tool_name, make_tool(next_node))

class GenericAgent(Agent):
    def __init__(self, prompt: str, tools: Optional[list] = None, chat_ctx=None, agent_config=None, node_config=None):
        global_prompt = agent_config.global_settings.global_prompt if agent_config.global_settings else ""
        llm_config = agent_config.global_settings.llm if agent_config.global_settings else None
        tts_config = agent_config.global_settings.tts if agent_config.global_settings else None

        llm_instance = build_llm_instance(llm_config.provider, llm_config.model, llm_config.api_key)
        tts_instance = build_tts_instance(tts_config.provider, tts_config.model, tts_config.language)

        self._agent_config = agent_config
        self._node_config = node_config

        super().__init__(
            instructions=f"{global_prompt}\n{prompt}",
            llm=llm_instance,
            tts=tts_instance,
            tools=tools or [],
            chat_ctx=chat_ctx
        )

    async def on_enter(self):
        await self.session.generate_reply()


async def create_agent(node_id: str, chat_ctx=None, agent_config=None, agent_id=None) -> Agent:
    tools = []

    if getattr(agent_config, "vector_store_id", None):
        try:
            query_tool = build_query_tool(agent_config.vector_store_id)
            tools.append(query_tool)
            print(f"Added query tool for vector store ID: {agent_config.vector_store_id}")
        except Exception as e:
            logger.error(f"Failed to load vector store tool: {e}")

    agent_flow = {node.node_id: node for node in agent_config.nodes}

    if node_id not in agent_flow:
        raise ValueError(f"Node '{node_id}' not found. Available nodes: {list(agent_flow.keys())}")

    node_config = agent_flow[node_id]
    node_type = node_config.type
    prompt = node_config.prompt or node_config.static_sentence or ""

    if node_config.routes:
        module = sys.modules[__name__]
        await generate_function_tools(node_config.dict(), module, agent_id)
        for route in node_config.routes:
            tools.append(getattr(module, route.tool_name))

    # if getattr(node_config, "is_exit_node", False):
    tools.append(end_call)

    if agent_id:
        await ws_manager.send_node_update(agent_id, node_id)
        all_bookings = list_orders()
        print("----------------------------")
        print(all_bookings)
        print("----------------------------")

    if node_type == "conversation":
        return GenericAgent(
            prompt=prompt,
            tools=tools,
            chat_ctx=chat_ctx,
            agent_config=agent_config,
            node_config=node_config
        )

    elif node_type == "function":
        # Expecting a callable named `node_config.function_name` in your code
        prompt = node_config.prompt or node_config.static_sentence or ""
        tools.append(place_order)

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
    agent_id = ctx.proc.userdata["agent_id"]
    raw_config = get_agent_config(agent_id)
    if not raw_config:
        logger.error(f"Agent config not found for ID: {agent_id}")
        return
    agent_config = AgentConfig(**raw_config)

    if not agent_config.nodes or not agent_config.global_settings:
        logger.error(f"Incomplete agent config for flow execution: {agent_id}")
        return

    logger.info(f"Starting session in room: {ctx.room.name} with agent ID: {agent_id}")
    await ctx.connect()

    stt_config = agent_config.global_settings.stt
    llm_config = agent_config.global_settings.llm
    tts_config = agent_config.global_settings.tts

    llm_instance = build_llm_instance(llm_config.provider, llm_config.model, llm_config.api_key)
    stt_instance = build_stt_instance(stt_config.provider, stt_config.model, stt_config.language, stt_config.api_key)
    tts_instance = build_tts_instance(tts_config.provider, tts_config.model, tts_config.language)

    session = AgentSession(
        stt=stt_instance,
        llm=llm_instance,
        tts=tts_instance,
        vad=silero.VAD.load()
    )
    session._agent_config = agent_config

    async def write_transcript():
        try:
            current_date = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_dir = os.path.join(os.getcwd(), "transcripts")
            os.makedirs(output_dir, exist_ok=True)
            file_path = os.path.join(output_dir, f"transcript_{ctx.room.name}_{current_date}.json")

            with open(file_path, "w") as f:
                json.dump(session.history.to_dict(), f, indent=2)

            logger.info(f"Transcript saved at: {file_path}")
        except Exception as e:
            logger.error(f"Failed to write transcript: {e}")

    ctx.add_shutdown_callback(write_transcript)

    entry_node_id = agent_config.entry_node
    if not entry_node_id and agent_config.nodes:
        entry_node_id = next(
            (node.node_id for node in agent_config.nodes if node.is_start_node),
            agent_config.nodes[0].node_id if agent_config.nodes else None
        )

    if not entry_node_id:
        logger.error("No entry node found in the configuration")
        return

    starting_agent = await create_agent(entry_node_id, agent_config=agent_config, agent_id=agent_id)
    await session.start(agent=starting_agent, room=ctx.room)

async def agent_run(agent_name: str,room_name:str, agent_id: Optional[str] = None):
    if not agent_id:
        logger.error("Agent ID is required")
        return

    def prewarm_fnc(proc):
        proc.userdata["agent_id"] = agent_id
        proc.userdata["room_name"] = room_name

    worker_options = WorkerOptions(
        entrypoint_fnc=entrypoint,
        ws_url=settings.LIVEKIT_URL,
        agent_name=agent_name,
        api_key=settings.LIVEKIT_API_KEY,
        api_secret=settings.LIVEKIT_API_SECRET,
        prewarm_fnc=prewarm_fnc
    )

    worker = Worker(opts=worker_options)
    await worker.run()