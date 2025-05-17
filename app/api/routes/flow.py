from fastapi import APIRouter, HTTPException, BackgroundTasks
from app.utils.mongodb_client import MongoDBClient
from app.core.agent_runner import agent_run
from app.utils.token import get_token, generate_ws_token
import uuid
import logging
import asyncio
from datetime import datetime
from livekit.api import LiveKitAPI, DeleteRoomRequest
from app.core.settings import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("agent-runner")

router = APIRouter()
mongo_client = MongoDBClient()
mongo_client.connect()

agent_sessions = {}

@router.post("/start-agent/{agent_id}")
async def start_agent_from_mongo(agent_id: str, background_tasks: BackgroundTasks):
    flow = mongo_client.get_flow_by_id(agent_id)

    if not flow:
        raise HTTPException(status_code=404, detail="Agent config not found in MongoDB")

    try:
        # tts_api_key = flow.get("global_settings", {}).get("tts", {}).get("api_key")
        # if isinstance(tts_api_key, dict):
        #     pk = tts_api_key.get("private_key")
        #     if pk and "\\n" in pk:
        #         tts_api_key["private_key"] = pk.replace("\\n", "\n")

        room_name = f"room-{uuid.uuid4().hex[:6]}"
        agent_name = f"agent-{uuid.uuid4().hex[:6]}"
        identity = f"user-{uuid.uuid4().hex[:6]}"

        token = get_token(agent=agent_name, agent_id=agent_id, identity=identity, room=room_name)
        ws_token = generate_ws_token(agent_id)

        task = asyncio.create_task(agent_run(agent_name=agent_name, agent_id=agent_id))
        agent_sessions[agent_id] = {
            "active": True,
            "status": "connected",
            "room_name": room_name,
            "started_at": datetime.now().isoformat(),
            "task": task
        }

        return {
            "status": "success",
            "agent_id": agent_id,
            "token": token,
            "ws_token": ws_token,
            "agent_name": agent_name,
            "room_name": room_name,
            "message": "Agent started successfully from MongoDB config"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start agent: {str(e)}")


@router.post("/stop-agent/{agent_id}")
async def disconnect_agent(agent_id: str):
    agent_info = agent_sessions.get(agent_id)

    if not agent_info:
        logger.warning(f"Agent {agent_id} not found for disconnection.")
        raise HTTPException(status_code=404, detail="Agent not found")

    room_name = agent_info.get("room_name")

    try:
        async with LiveKitAPI(
            url=settings.LIVEKIT_URL,
            api_key=settings.LIVEKIT_API_KEY,
            api_secret=settings.LIVEKIT_API_SECRET
        ) as lkapi:
            await lkapi.room.delete_room(DeleteRoomRequest(room=room_name))
            logger.info(f"Room '{room_name}' deleted from LiveKit.")
    except Exception as e:
        logger.error(f"Failed to delete room '{room_name}': {e}")

    task = agent_info.get("task")
    if task and not task.done():
        try:
            logger.info(f"Cancelling background task for agent {agent_id}...")
            task.cancel()
            await task
        except asyncio.CancelledError:
            logger.info(f"Task for agent {agent_id} cancelled.")
        except Exception as e:
            logger.exception(f"Error while cancelling task for agent {agent_id}: {str(e)}")

    # 🗂 Update status
    agent_info.update({
        "active": False,
        "status": "disconnected",
        "room_name": None,
        "task": None
    })

    logger.info(f"Agent {agent_id} disconnected successfully.")
    return {
        "status": "success",
        "message": f"Agent {agent_id} disconnected"
    }
