import logging
import sys
from typing import Optional, Dict, Any
from dataclasses import dataclass
from datetime import datetime
import json
import os
from livekit.agents import Worker
from livekit import api
from livekit.agents import JobContext, WorkerOptions, cli
from livekit.agents.llm import function_tool
from livekit.agents.voice import Agent, AgentSession, RunContext
from livekit.plugins import openai, google, deepgram, silero
from google.cloud.texttospeech import VoiceSelectionParams
from app.core.config import get_agent_config 

LIVEKIT_API_KEY="APIYzqLsmBChBFz"
LIVEKIT_API_SECRET="eVTStfVzKiQ1lTzVWxebpxzCKM5M6JFCesXJdJXZb4OA"
LIVEKIT_URL="wss://algo-vox-a45ok1i2.livekit.cloud"


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("agent-runner")

async def generate_function_tools(config, module):
    for route in config.get("routes", []):
        tool_name = route["tool_name"]
        next_node = route["next_node"]
        tool_definition = route.get("condition", "")

        def make_tool(next_node_val):
            @function_tool(name=tool_name, description=f"Use this tool if {tool_definition}")
            async def tool_fn(context: RunContext):
                chat_ctx = context.session._chat_ctx
                return await create_agent(next_node_val, chat_ctx=chat_ctx, agent_config=context.session._agent_config)
            return tool_fn

        setattr(module, tool_name, make_tool(next_node))

class GenericAgent(Agent):
    def __init__(self, prompt: str, tools: Optional[list] = None, chat_ctx=None, agent_config=None, node_config=None):
        global_prompt = agent_config.get("global_settings", {}).get("global_prompt", "")
        llm_config = agent_config.get("global_settings", {}).get("llm", {})
        tts_config = agent_config.get("global_settings", {}).get("tts", {})
        
        llm_provider = llm_config.get("provider", "openai")
        llm_model = llm_config.get("model", "gpt-4o-mini")
        llm_api_key=llm_config.get("api_key")

        # # if llm_provider == "groq":
        # #     llm_instance = groq.LLM(model=llm_model)
        # else:
        llm_instance = openai.LLM(model=llm_model,api_key=llm_api_key)
        # Configure TTS
        tts_provider = tts_config.get("provider", "google")
        tts_voice = tts_config.get("model", "en-US-Wavenet-F")
        tts_language = tts_config.get("language", "en-US")
        
        if tts_provider == "google":
            tts_instance = google.TTS(
                voice=VoiceSelectionParams(
                    name=tts_voice,
                    language_code=tts_language
                )
            )
        else:
            # Default to Google TTS
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
        # Check if we should speak first
        # speak_order = self._node_config.get("speak_order", None)
        # if speak_order == "ai_first":
        await self.session.generate_reply()

async def create_agent(node_id: str, chat_ctx=None, agent_config=None) -> Agent:
    agent_flow = {node["node_id"]: node for node in agent_config.get("nodes", [])}
    
    if node_id not in agent_flow:
        raise ValueError(f"Node '{node_id}' not found. Available nodes: {list(agent_flow.keys())}")

    node_config = agent_flow[node_id]
    prompt = node_config.get("prompt") or node_config.get("static_sentence", "")
    tools = []

    if "routes" in node_config:
        module = sys.modules[__name__]
        await generate_function_tools(node_config, module)
        for route in node_config["routes"]:
            tools.append(getattr(module, route["tool_name"]))

    return GenericAgent(
        prompt=prompt, 
        tools=tools, 
        chat_ctx=chat_ctx, 
        agent_config=agent_config,
        node_config=node_config
    )

async def entrypoint(ctx: JobContext):
    agent_id = agent_id_g
    agent_config = get_agent_config(agent_id)
    
    if not agent_config:
        logger.error(f"Agent config not found for ID: {agent_id}")
        return

    logger.info(f"Starting session in room: {ctx.room.name} with agent ID: {agent_id}")
    await ctx.connect()

    # Get STT config
    stt_config = agent_config.get("global_settings", {}).get("stt", {})
    stt_provider = stt_config.get("provider", "deepgram")
    stt_model = stt_config.get("model", "nova-3")
    stt_language = stt_config.get("language", "en")
    stt_api_key=stt_config.get("api_key")

    # Get LLM config
    llm_config = agent_config.get("global_settings", {}).get("llm", {})
    llm_provider = llm_config.get("provider", "openai")
    llm_model = llm_config.get("model", "gpt-4o-mini")
    llm_api_key=llm_config.get("api_key")

    # Get TTS config
    tts_config = agent_config.get("global_settings", {}).get("tts", {})
    tts_provider = tts_config.get("provider", "google")
    tts_voice = tts_config.get("model", "en-US-Wavenet-F") 
    tts_language = tts_config.get("language", "en-US")

    # Configure STT
    if stt_provider == "deepgram":
        stt_instance = deepgram.STT(model=stt_model, language=stt_language,api_key=stt_api_key)
    else:
        # Default to Deepgram
        stt_instance = deepgram.STT(model="nova-3", language="en",api_key=stt_api_key)
    
    # Configure LLM
    # if llm_provider == "groq":
    #     llm_instance = groq.LLM(model=llm_model)
    # else:
    llm_instance = openai.LLM(model=llm_model,api_key=llm_api_key)
    
    # Configure TTS
    if tts_provider == "google":
        tts_instance = google.TTS(
            voice=VoiceSelectionParams(
                name=tts_voice,
                language_code=tts_language
            )
        )
    else:
        # Default to Google TTS
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
    
    # Add agent config to session for access by tools
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

    entry_node_id = agent_config.get("entry_node")
    if not entry_node_id:
        # Find the start node if entry_node is not specified
        nodes = agent_config.get("nodes", [])
        entry_node_id = next(
            (node["node_id"] for node in nodes if node.get("is_start_node") is True), 
            nodes[0]["node_id"] if nodes else None
        )
    
    if not entry_node_id:
        logger.error("No entry node found in the configuration")
        return

    starting_agent = await create_agent(entry_node_id, agent_config=agent_config)
    await session.start(agent=starting_agent, room=ctx.room)

async def agent_run(agent_name: Optional[str] = None, agent_id: Optional[str] = None):
    if not agent_id:
        logger.error("Agent ID is required")
        return
    global agent_id_g
    agent_id_g = agent_id
        
    worker_options = WorkerOptions(
        entrypoint_fnc=entrypoint,
        ws_url=LIVEKIT_URL,  # Replace with your LiveKit WebSocket URL
        agent_name=agent_name or f"agent_{agent_id}",
        api_key=LIVEKIT_API_KEY,
        api_secret=LIVEKIT_API_SECRET,
    )
    
    worker = Worker(opts=worker_options)
    await worker.run()