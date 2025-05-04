import logging
import sys
from typing import Optional
from dataclasses import dataclass
from datetime import datetime
import json
from livekit.agents import Worker
import os
from dotenv import load_dotenv
from livekit import api
from livekit.agents import JobContext, WorkerOptions, cli
from livekit.agents.llm import function_tool
from livekit.agents.voice import Agent, AgentSession, RunContext
from livekit.plugins import openai, google, deepgram, silero
from google.cloud.texttospeech import VoiceSelectionParams
from app.core.config import AGENT_CONFIG, load_config

load_dotenv()
load_config()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("agent-runner")
logger.info("Starting agent runner...")

raw_agent_flow = AGENT_CONFIG.get("nodes", [])
global_prompt = AGENT_CONFIG.get("global_prompt", "")

entry_node_id = AGENT_CONFIG.get("entry_node") or (
    next((node["node_id"] for node in raw_agent_flow if node.get("is_start_node") is True), raw_agent_flow[0]["node_id"] if raw_agent_flow else None)
)

# if not raw_agent_flow:
#     raise ValueError("AGENT_CONFIG['nodes'] is empty. Did you call /configure-flow/ before /start-agent/?")

agent_flow = {node["node_id"]: node for node in raw_agent_flow}

# if entry_node_id not in agent_flow:
#     raise ValueError(f"Missing required entry node '{entry_node_id}' in agent flow. Available nodes: {list(agent_flow.keys())}")

def generate_function_tools(config):
    module = sys.modules[__name__]
    for route in config.get("routes", []):
        tool_name = route["tool_name"]
        next_node = route["next_node"]
        tool_definition= route.get("condition", None)

        def make_tool(next_node_val):
            @function_tool(name=tool_name,description=f"Use this tool if {tool_definition}")
            async def tool_fn(context: RunContext):
                chat_ctx = context.session._chat_ctx
                return create_agent(next_node_val, chat_ctx=chat_ctx)
            return tool_fn

        setattr(module, tool_name, make_tool(next_node))

class GenericAgent(Agent):
    def __init__(self, prompt: str, tools: Optional[list] = None, chat_ctx=None, config=None):
        llm_provider = config.get("llm_provider", "openai")
        llm_model = config.get("llm_model", "gpt-4o-mini")

        if llm_provider == "groq":
            from livekit.plugins import groq
            llm_instance = groq.LLM(model=llm_model)
        else:
            llm_instance = openai.LLM(model=llm_model)

        super().__init__(
            instructions=f"{global_prompt}\n{prompt}",
            llm=llm_instance,
            tts=google.TTS(
                voice=VoiceSelectionParams(
                    name="en-IN-Chirp3-HD-Charon",
                    language_code="en-IN"
                )
            ),
            tools=tools or [],
            chat_ctx=chat_ctx
        )

    async def on_enter(self):
        await self.session.generate_reply()

def create_agent(name: str, chat_ctx=None) -> Agent:
    if name not in agent_flow:
        raise ValueError(f"Node '{name}' not found. Available nodes: {list(agent_flow.keys())}")

    config = agent_flow[name]
    prompt = config.get("prompt") or config.get("static_sentence", "")
    tools = []

    if "routes" in config:
        generate_function_tools(config)
        for route in config["routes"]:
            tools.append(getattr(sys.modules[__name__], route["tool_name"]))

    return GenericAgent(prompt=prompt, tools=tools, chat_ctx=chat_ctx, config=config)

async def entrypoint(ctx: JobContext):
    logger.info(f"Starting session in room: {ctx.room.name}")
    await ctx.connect()

    session = AgentSession(
        stt=deepgram.STT(model="nova-3", language="en"),
        llm=openai.LLM(model="gpt-4o-mini"),
        tts=google.TTS(
            voice=VoiceSelectionParams(
                name="en-IN-Chirp3-HD-Charon",
                language_code="en-IN"
            )
        ),
        vad=silero.VAD.load()
    )

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

    starting_agent = create_agent(entry_node_id)
    await session.start(agent=starting_agent, room=ctx.room)

async def agent_run(agent_name:Optional[str] = None, token: Optional[str] = None):

    worker_options = WorkerOptions(
        entrypoint_fnc=entrypoint,
        ws_url="wss://alice-sjgt0raw.livekit.cloud",
        agent_name=agent_name,
    )
    worker = Worker(
        opts=worker_options,
    )
    await worker.run()

if __name__ == "__main__":
    import asyncio
    asyncio.run(agent_run())
