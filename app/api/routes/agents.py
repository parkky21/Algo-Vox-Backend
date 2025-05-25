from fastapi import APIRouter, HTTPException, BackgroundTasks
from app.utils.mongodb_client import MongoDBClient
from app.core.start_agent import agent_run
from app.utils.token import get_token, generate_ws_token
import uuid
import logging
import asyncio
from datetime import datetime
from livekit.api import LiveKitAPI, DeleteRoomRequest
from app.core.config import settings
from app.utils.vector_store_utils import vector_stores
from app.utils.node_parser import parse_agent_config
from app.utils.validators import validate_custom_function
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("agent-runner")

router = APIRouter()
mongo_client = MongoDBClient()

agent_sessions = {}

from pydantic import ValidationError

@router.post("/start-agent/{agent_id}")
async def start_agent_from_mongo(agent_id: str, background_tasks: BackgroundTasks):
    flow = mongo_client.get_flow_by_id(agent_id)

    if not flow:
        raise HTTPException(
            status_code=404,
            detail=f"Agent configuration with ID '{agent_id}' not found in MongoDB"
        )

    try:
        agent_config = parse_agent_config(flow)
        
        for node in agent_config.nodes or []:
            if node.type == "function" and node.custom_function:
                validate_custom_function(node.custom_function.get("fnc_code", ""))

        vector_store_id = getattr(agent_config.global_settings, "vector_store_id", None)
        if vector_store_id and vector_store_id not in vector_stores:
            raise HTTPException(
                status_code=400,
                detail=f"Vector store ID '{vector_store_id}' is not loaded in memory. "
                       f"Please ensure it's created and loaded before running the agent."
            )

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
            "message": "Agent successfully launched from MongoDB configuration"
        }

    except ValidationError as ve:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid agent configuration: {ve.errors()}"
        )
    except HTTPException:
        raise  # re-raise any manually raised HTTPExceptions (e.g., for vector_store_id)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Unexpected error while starting agent '{agent_id}': {str(e)}"
        )


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
