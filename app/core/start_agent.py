from typing import Optional
import logging
from livekit.agents import Worker, WorkerOptions, JobProcess
from app.core.config import settings
from app.core.entrypoints import entrypoint 
from livekit.plugins import silero
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("agent-runner")

async def agent_run(agent_name: str, agent_id: Optional[str] = None):
    if not agent_id:
        logger.error("Agent ID is required")
        return
    
    # def prewarm(proc:JobProcess):
    #     proc.userdata["vad"] = silero.VAD.load()

    worker_options = WorkerOptions(
        entrypoint_fnc=entrypoint,
        ws_url=settings.LIVEKIT_URL,
        agent_name=agent_name,
        api_key=settings.LIVEKIT_API_KEY,
        api_secret=settings.LIVEKIT_API_SECRET,
        # prewarm_fnc=prewarm,
    )

    worker = Worker(opts=worker_options)
    await worker.run()