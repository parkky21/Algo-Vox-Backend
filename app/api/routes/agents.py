# app/api/routes/agents.py
from fastapi import APIRouter, HTTPException, BackgroundTasks, Body, Request
from typing import Dict, List, Optional, Any
from uuid import uuid4
from contextlib import asynccontextmanager
import asyncio
import uuid
import logging
import traceback
from app.core.full_flow3 import agent_run
from app.core.models import ModelParameter , AgentConfig,ModelConfig,ConnectAgentRequest
from app.utils.token import get_token
from livekit import api, agents
from app.core.config import AGENT_CONFIG,save_config
from app.core.agent_runner import KnowledgeBaseAgent, start_agent_session
router = APIRouter()
connect_router = APIRouter()


logger = logging.getLogger(__name__)
agent_sessions = {}

@asynccontextmanager
async def lifespan(app):
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

@router.post("")
async def create_agent(config: AgentConfig):
    agent_id = config.agent_id or str(uuid.uuid4())
    if agent_id in agent_sessions:
        raise HTTPException(status_code=400, detail="Agent ID already exists")

    agent_sessions[agent_id] = {
        "config": config.dict(),
        "status": "created",
        "vector_store_ids": config.vector_store_ids,
        "room_name": None,
        "active": False
    }
    return {"agent_id": agent_id, "status": "created"}

@router.get("")
async def list_agents():
    return [
        {
            "id": agent_id,
            "name": info["config"]["name"],
            "status": info["status"],
            "room_name": info["room_name"],
            "active": info["active"]
        }
        for agent_id, info in agent_sessions.items()
    ]

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

@router.post("/configure-flow/")
async def configure_flow(request: Request):
    body = await request.json()
    AGENT_CONFIG["nodes"] = body.get("nodes", [])
    AGENT_CONFIG["global_prompt"] = body.get("global_settings", {}).get("global_prompt", "")
    AGENT_CONFIG["entry_node"] = body.get("entry_node", "node_1")
    AGENT_CONFIG["room"] = body.get("room", "default-room")
    AGENT_CONFIG["agent_name"] = body.get("agent_name", "sukuna")

    save_config()

    return {
        "status": "Flow configured",
        "nodes_count": len(AGENT_CONFIG["nodes"]),
        "entry_node": AGENT_CONFIG["entry_node"],
        "room": AGENT_CONFIG["room"],
        "agent_name":AGENT_CONFIG["agent_name"]
    }

@connect_router.post("/connect_agent")
async def connect_agent(request: ConnectAgentRequest, background_tasks: BackgroundTasks):
    agent_id = request.agent_id
    if agent_id not in agent_sessions:
        raise HTTPException(status_code=404, detail="Agent not found")

    agent_info = agent_sessions[agent_id]
    if agent_info["active"]:
        raise HTTPException(status_code=400, detail="Agent already active")

    try:
        agent_info["connection_event"] = asyncio.Event()

        # ✅ Generate unique names
        unique_agent_name = f"agent-{uuid4().hex[:6]}"
        unique_room_name = f"room-{uuid4().hex[:6]}"
        print("gen comlpeye")

        # ✅ Generate LiveKit token with unique values
        token = get_token(
            agent=unique_agent_name,
            identity=agent_id,
            room=unique_room_name
        )

        print("tokncopy")
        background_tasks.add_task(agent_run, unique_agent_name, token)

        # ✅ Store names in session info
        # agent_info["room_name"] = unique_room_name
        # agent_info["unique_agent_name"] = unique_agent_name

        # ✅ Start background worker
        # background_tasks.add_task(
        #     start_agent_session,
        #     agent_id,
        #     unique_agent_name,
        #     unique_room_name,
        #     token,
        #     request.config
        # )


        # Wait for connection
        # try:
        #     await asyncio.wait_for(agent_info["connection_event"].wait(), timeout=60)
        # except asyncio.TimeoutError:
        #     return {"status": "error", "message": "Agent connection timeout"}

        # if agent_info["active"]:
        return {
            "status": "active",
            "token":token,
            "agent_id": agent_id,
            "room_name": unique_room_name,
            "agent_name": unique_agent_name
        }

        # return {"status": agent_info["status"], "message": "Agent connection failed"}

    except Exception as e:
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Connection error: {str(e)}")
    
@connect_router.post("/disconnect_agent/{agent_id}")
async def disconnect_agent(agent_id: str):
    if agent_id not in agent_sessions:
        raise HTTPException(status_code=404, detail="Agent not found")

    agent_info = agent_sessions[agent_id]
    if not agent_info["active"]:
        return {"status": "success", "message": "Agent not active"}

    if "task" in agent_info and not agent_info["task"].done():
        agent_info["task"].cancel()
        try:
            await agent_info["task"]
        except asyncio.CancelledError:
            pass

    agent_info["active"] = False
    agent_info["status"] = "disconnected"
    agent_info["room_name"] = None
    return {"status": "success", "message": "Agent disconnected"}
