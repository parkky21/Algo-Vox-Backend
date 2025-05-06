# app/api/routes/agents.py
from fastapi import APIRouter, HTTPException, BackgroundTasks, Body, Request
from typing import Dict, List, Optional, Any
from uuid import uuid4
from contextlib import asynccontextmanager
import asyncio
import uuid
import logging
from app.core.models import  AgentResponse, AgentConfig, StartAgentRequest,StopAgentRequest
from livekit import api
from livekit.api import DeleteRoomRequest, LiveKitAPI
from app.core.config import save_config,load_all_configs,get_agent_config
from app.core.agent_runner import agent_run
from app.core.settings import settings
from app.utils.token import get_token
router = APIRouter()
connect_router = APIRouter()


agent_configs: Dict[str, dict] = {}

logger = logging.getLogger(__name__)
agent_sessions = {}

@asynccontextmanager
async def lifespan(app):
    load_all_configs()
    app.state.lkapi = api.LiveKitAPI(
        url="wss://algo-vox-a45ok1i2.livekit.cloud",
        api_key="APIYzqLsmBChBFz",
        api_secret="eVTStfVzKiQ1lTzVWxebpxzCKM5M6JFCesXJdJXZb4OA",
    )
    yield
    for agent_id, session_info in list(agent_sessions.items()):
        if 'task' in session_info and not session_info['task'].done():
            session_info['task'].cancel()
    await app.state.lkapi._session.close()


@router.get("/{agent_id}")
async def get_agent(agent_id: str):
    if agent_id not in agent_sessions:
        raise HTTPException(status_code=404, detail="Agent not found")
    agent_info = agent_sessions[agent_id]
    return {
        "id": agent_id,
        "config": {
            k: v for k, v in agent_info["config"].items() 
            if not (isinstance(v, dict) and "api_key" in v)
        },
        "status": agent_info["status"],
        "room_name": agent_info["room_name"],
        "active": agent_info["active"],
        "vector_store_ids": agent_info["vector_store_ids"]
    }

@router.delete("/{agent_id}")
async def delete_agent(agent_id: str):
    if agent_id not in agent_sessions:
        raise HTTPException(status_code=404, detail="Agent not found")

    agent_info = agent_sessions[agent_id]
    if agent_info["active"] and "task" in agent_info:
        if not agent_info["task"].done():
            agent_info["task"].cancel()
            try:
                await agent_info["task"]
            except asyncio.CancelledError:
                pass

    del agent_sessions[agent_id]
    return {"status": "deleted", "agent_id": agent_id}

@router.post("/configure", response_model=AgentResponse)
async def configure_agent(config: AgentConfig):
    """Configure an agent and get a unique agent ID"""
    try:
        agent_id = str(uuid.uuid4())
        agent_configs[agent_id] = config.dict()
        agent_name = f"agent-{uuid.uuid4().hex[:6]}"
        room_name = f"room-{uuid.uuid4().hex[:6]}"

        # Save configuration to disk
        save_config(agent_id, agent_configs[agent_id],room_name=room_name,agent_name=agent_name)

        logger.info(f"Configured agent with ID: {agent_id}")
        return AgentResponse(
            agent_id=agent_id,
            message="Agent configured successfully"
        )
    except Exception as e:
        logger.exception("Failed to configure agent")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@router.post("/start-agent")
async def start_agent(request: StartAgentRequest):
    agent_id = request.agent_id

    try:
        # 1. Load agent config from disk
        config = get_agent_config(agent_id)
        if not config:
            logger.warning(f"Agent config not found for ID: {agent_id}")
            raise HTTPException(status_code=404, detail="Agent config not found")

        # 2. Store it in in-memory cache (optional but useful)
        agent_configs[agent_id] = config
        agent_name = f"agent-{uuid.uuid4().hex[:6]}"
        room_name = f"room-{uuid.uuid4().hex[:6]}"
        config["agent_name"]=agent_name
        config["room_name"]=room_name

        # 3. Generate session-specific identifiers

        identity = f"user-{uuid.uuid4().hex[:6]}"

        # 4. Generate LiveKit token
        logger.info(f"Generating token for agent {agent_name} in room {room_name}...")
        try:
            token = get_token(agent=agent_name, identity=identity, room=room_name)
        except Exception:
            logger.exception("Failed to generate LiveKit token")
            raise HTTPException(status_code=500, detail="Error generating access token")

        # 5. Start agent session as a background task
        logger.info(f"Starting background task for agent {agent_name}...")
        try:
            task = asyncio.create_task(agent_run(agent_name=agent_name, agent_id=agent_id))
            agent_sessions[agent_id] = {
                "active": True,
                "status": "connected",
                "room_name": room_name,
                "task": task
            }
        except Exception:
            logger.exception("Failed to start background task for agent")
            raise HTTPException(status_code=500, detail="Failed to start agent background process")

        # 6. Return success
        return {
            "status": "success",
            "token": token,
            "agent_name": agent_name,
            "room_name": room_name,
            "message": f"Agent {agent_id} started successfully"
        }

    except HTTPException as http_err:
        raise http_err

    except Exception as e:
        logger.exception("Unexpected error in start-agent")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@router.post("/disconnect")
async def disconnect_agent(request: StopAgentRequest):
    agent_id = request.agent_id
    config=get_agent_config(agent_id)
    room_name=config.get("room_name")
    agent_info = agent_sessions.get(agent_id)

    if not agent_info:
        logger.warning(f"Agent {agent_id} not found for disconnection.")
        raise HTTPException(status_code=404, detail="Agent not found")
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

    if not agent_info.get("active", False):
        logger.info(f"Agent {agent_id} is already inactive.")
        return {"status": "success", "message": "Agent already inactive"}

    task = agent_info.get("task")
    if task and not task.done():
        logger.info(f"Cancelling background task for agent {agent_id}...")
        try:
            task.cancel()
            await task
        except asyncio.CancelledError:
            logger.info(f"Task for agent {agent_id} cancelled.")
        except Exception as e:
            logger.exception(f"Error while cancelling task for agent {agent_id}: {str(e)}")

    agent_info.update({
        "active": False,
        "status": "disconnected",
        "room_name": None,
        "task": None
    })

    logger.info(f"Agent {agent_id} disconnected successfully.")
    return {"status": "success", "message": f"Agent {agent_id} disconnected"}