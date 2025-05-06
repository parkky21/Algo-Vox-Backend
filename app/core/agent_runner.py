import logging
import sys
from typing import Optional
from dataclasses import dataclass
from datetime import datetime
import json
import os
from livekit.agents import Worker
from livekit import api
from livekit.agents import JobContext, WorkerOptions
from livekit.agents.llm import function_tool
from livekit.agents.voice import Agent, AgentSession, RunContext
from livekit.plugins import openai, google, deepgram, silero
from google.cloud.texttospeech import VoiceSelectionParams
from app.core.config import get_agent_config 
from app.core.models import AgentConfig
from app.core.ws_manager import ws_manager

LIVEKIT_API_KEY = "APIYzqLsmBChBFz"
LIVEKIT_API_SECRET = "eVTStfVzKiQ1lTzVWxebpxzCKM5M6JFCesXJdJXZb4OA"
LIVEKIT_URL = "wss://algo-vox-a45ok1i2.livekit.cloud"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("agent-runner")

async def generate_function_tools(config, module,agent_id):
    for route in config.get("routes", []):
        tool_name = route["tool_name"]
        next_node = route["next_node"]
        tool_definition = route.get("condition", "")

        def make_tool(next_node_val):
            @function_tool(name=tool_name, description=f"Use this tool if {tool_definition}")
            async def tool_fn(context: RunContext):
                chat_ctx = context.session._chat_ctx
                return await create_agent(next_node_val, chat_ctx=chat_ctx, agent_config=context.session._agent_config,agent_id=agent_id)
            return tool_fn

        setattr(module, tool_name, make_tool(next_node))

class GenericAgent(Agent):
    def __init__(self, prompt: str, tools: Optional[list] = None, chat_ctx=None, agent_config=None, node_config=None):
        global_prompt = agent_config.global_settings.global_prompt if agent_config.global_settings else ""
        llm_config = agent_config.global_settings.llm if agent_config.global_settings else None
        tts_config = agent_config.global_settings.tts if agent_config.global_settings else None

        llm_provider = llm_config.provider
        llm_model = llm_config.model
        llm_api_key = llm_config.api_key

        llm_instance = openai.LLM(model=llm_model, api_key=llm_api_key)

        tts_provider = tts_config.provider
        tts_voice = tts_config.model
        tts_language = tts_config.language

        if tts_provider == "google":
            tts_instance = google.TTS(
                voice=VoiceSelectionParams(
                    name=tts_voice,
                    language_code=tts_language
                )
            )
        else:
            tts_instance = google.TTS(
                voice=VoiceSelectionParams(
                    name="en-US-Wavenet-F",
                    language_code="en-US"
                )
            )

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

async def create_agent(node_id: str, chat_ctx=None, agent_config=None,agent_id=None) -> Agent:
    agent_flow = {node.node_id: node for node in agent_config.nodes}

    if node_id not in agent_flow:
        raise ValueError(f"Node '{node_id}' not found. Available nodes: {list(agent_flow.keys())}")

    node_config = agent_flow[node_id]
    prompt = node_config.prompt or node_config.static_sentence or ""
    tools = []

    if node_config.routes:
        module = sys.modules[__name__]
        await generate_function_tools(node_config.dict(), module,agent_id)
        for route in node_config.routes:
            tools.append(getattr(module, route.tool_name))

    if agent_id:
        await ws_manager.send_node_update(
            agent_id,
            node_id
            )

    return GenericAgent(
        prompt=prompt, 
        tools=tools, 
        chat_ctx=chat_ctx, 
        agent_config=agent_config,
        node_config=node_config
    )

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
    stt_provider = stt_config.provider
    stt_model = stt_config.model
    stt_language = stt_config.language
    stt_api_key = stt_config.api_key

    llm_config = agent_config.global_settings.llm
    llm_provider = llm_config.provider
    llm_model = llm_config.model
    llm_api_key = llm_config.api_key

    tts_config = agent_config.global_settings.tts
    tts_provider = tts_config.provider
    tts_voice = tts_config.model
    tts_language = tts_config.language

    if stt_provider == "deepgram":
        stt_instance = deepgram.STT(model=stt_model, language=stt_language, api_key=stt_api_key)
    else:
        stt_instance = deepgram.STT(model="nova-3", language="en", api_key=stt_api_key)

    llm_instance = openai.LLM(model=llm_model, api_key=llm_api_key)

    if tts_provider == "google":
        tts_instance = google.TTS(
            voice=VoiceSelectionParams(
                name=tts_voice,
                language_code=tts_language
            )
        )
    else:
        tts_instance = google.TTS(
            voice=VoiceSelectionParams(
                name="en-US-Wavenet-F",
                language_code="en-US"
            )
        )

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

    starting_agent = await create_agent(entry_node_id, agent_config=agent_config,agent_id=agent_id)
    await session.start(agent=starting_agent, room=ctx.room)

async def agent_run(agent_name: Optional[str] = None, agent_id: Optional[str] = None):
    if not agent_id:
        logger.error("Agent ID is required")
        return

    def prewarm_fnc(proc):
        proc.userdata["agent_id"] = agent_id

    worker_options = WorkerOptions(
        entrypoint_fnc=entrypoint,
        ws_url=LIVEKIT_URL,
        agent_name=agent_name,
        api_key=LIVEKIT_API_KEY,
        api_secret=LIVEKIT_API_SECRET,
        prewarm_fnc=prewarm_fnc
    )

    worker = Worker(opts=worker_options)
    await worker.run()
