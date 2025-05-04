# app/core/agent_runner.py
import asyncio
import logging
import traceback
from typing import Optional, Dict, List
from livekit import agents
from livekit.agents import AutoSubscribe, JobContext, Agent, AgentSession
from livekit.plugins import deepgram, google, silero, turn_detector
from app.api.routes.vector_stores import vector_stores

logger = logging.getLogger(__name__)


LIVEKIT_API_KEY="APIYzqLsmBChBFz"
LIVEKIT_API_SECRET="eVTStfVzKiQ1lTzVWxebpxzCKM5M6JFCesXJdJXZb4OA"
LIVEKIT_URL="wss://algo-vox-a45ok1i2.livekit.cloud"


class KnowledgeBaseAgent(agents.Agent):
    def __init__(self, agent_id: str, instructions: str, vector_store_ids: List[str], room_name: str) -> None:
        super().__init__(instructions=instructions)
        self.agent_id = agent_id
        self.vector_store_ids = vector_store_ids
        self.agent_instructions = instructions
        self.room_name = room_name

    async def entrypoint(self, ctx: JobContext) -> None:
        await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)

        from app.api.routes.agents import agent_sessions
        if self.agent_id in agent_sessions:
            agent_sessions[self.agent_id]["active"] = True
            agent_sessions[self.agent_id]["status"] = "connected"
            agent_sessions[self.agent_id]["room_name"] = self.room_name
            if "connection_event" in agent_sessions[self.agent_id]:
                agent_sessions[self.agent_id]["connection_event"].set()

        kb_stores = [store_id for store_id in self.vector_store_ids if store_id in vector_stores]

        kb_instructions = self.agent_instructions
        if kb_stores:
            kb_instructions += "\nYou have access to knowledge bases that you can query for information."

        stt = tts = llm = None
        vad = silero.VAD.load()

        agent_config = agent_sessions.get(self.agent_id, {}).get("config", {})

        stt_config = agent_config.get("STT", {})
        if stt_config:
            provider = stt_config.get("provider", "").lower()
            model_name = stt_config.get("model_name", "")
            api_key = next((param["value"] for param in stt_config.get("additionalParameters", [])
                            if param["key"] == "api_key"), None)
            if provider == "deepgram" and api_key:
                stt = deepgram.STT(model=model_name or "nova-2-general", language="multi", api_key=api_key)

        tts_config = agent_config.get("TTS", {})
        if tts_config:
            provider = tts_config.get("provider", "").lower()
            model_name = tts_config.get("model_name", "")
            api_key = next((param["value"] for param in tts_config.get("additionalParameters", [])
                            if param["key"] == "api_key"), None)
            if provider == "deepgram" and api_key:
                tts = deepgram.TTS(model=model_name or "aura-asteria-en", api_key=api_key)

        llm_config = agent_config.get("LLM", {})
        if llm_config:
            provider = llm_config.get("provider", "").lower()
            model_name = llm_config.get("model_name", "")
            api_key = next((param["value"] for param in llm_config.get("additionalParameters", [])
                            if param["key"] == "api_key"), None)
            if provider == "google" and api_key:
                llm = google.LLM(model=model_name or "gemini-1.5-pro", api_key=api_key)

        try:
            agent = Agent(
                stt=stt,
                llm=llm,
                tts=tts,
                vad=vad,
                turn_detection=turn_detector.EOUModel(),
                instructions=kb_instructions
            )
            session = AgentSession()
            await session.start(
                room=ctx.room,
                agent=agent
            )
            await session.say("Hey, This is Algo-Vox How can I help you?", allow_interruptions=True)

        except Exception as e:
            logger.error(traceback.format_exc())
            logger.error(f"Error in conversation pipeline: {str(e)}")
        finally:
            if self.agent_id in agent_sessions:
                agent_sessions[self.agent_id]["active"] = False
                agent_sessions[self.agent_id]["status"] = "disconnected"
                agent_sessions[self.agent_id]["room_name"] = None

async def start_agent_session(agent_id: str,agent_name:str, room_name: str, token: str, config: Optional[Dict] = None):
    from app.api.routes.agents import agent_sessions
    if agent_id not in agent_sessions:
        logger.error(f"Agent {agent_id} not found during session start")
        return

    agent_info = agent_sessions[agent_id]
    agent_config = agent_info["config"]
    try:
        agent = KnowledgeBaseAgent(
            agent_id=agent_id,
            instructions=agent_config["instructions"],
            vector_store_ids=agent_info["vector_store_ids"],
            room_name=room_name
        )
        agent_info["active"] = True
        agent_info["status"] = "connecting"
        agent_info["room_name"] = room_name


        worker = agents.Worker(
            opts=agents.WorkerOptions(
                entrypoint_fnc=agent.entrypoint, 
                ws_url="wss://algo-vox-a45ok1i2.livekit.cloud",
                agent_name=agent_name,
                api_key=LIVEKIT_API_KEY,
                api_secret=LIVEKIT_API_SECRET
                )
        )
        agent_info["worker"] = worker
        # worker.simulate_job(info=token)
        await worker.run()

    except asyncio.CancelledError:
        logger.info(f"Agent {agent_id} session was cancelled")
        raise
    except Exception as e:
        logger.error(f"Error in agent {agent_id} session: {str(e)}")
    finally:
        if agent_id in agent_sessions:
            agent_sessions[agent_id]["active"] = False
            agent_sessions[agent_id]["status"] = "disconnected"
            agent_sessions[agent_id]["room_name"] = None
