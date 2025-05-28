from fastapi import APIRouter, HTTPException, BackgroundTasks
from app.utils.mongodb_client import MongoDBClient
import uuid
import logging
import asyncio
from datetime import datetime
from app.utils.vector_store_utils import vector_stores
from app.utils.node_parser import parse_agent_config
from app.utils.validators import validate_custom_function
from app.utils.dispatch_service import create_agent_dispatch
from app.core.start_agent import agent_run
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("agent-runner")
from fastapi import Body

router = APIRouter()
mongo_client = MongoDBClient()

agent_sessions = {}

from pydantic import ValidationError

@router.post("/start-call/{agent_id}")
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
                validate_custom_function(node.custom_function.code)

        vector_store_id = getattr(agent_config.global_settings, "vector_store_id", None)
        if vector_store_id and vector_store_id not in vector_stores:
            raise HTTPException(
                status_code=400,
                detail=f"Vector store ID '{vector_store_id}' is not loaded in memory. "
                       f"Please ensure it's created and loaded before running the agent."
            )

        room_name = f"room-{uuid.uuid4().hex[:6]}"
        agent_name = f"agent-{uuid.uuid4().hex[:6]}"
        phn_num= "+918108709605"  # Example phone number, replace as needed
        
        task = asyncio.create_task(agent_run(agent_name=agent_name, agent_id=agent_id))
        dispatch = await create_agent_dispatch(agent_id=agent_id,phone_number=phn_num, agent_name=agent_name, room_name=room_name)

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
            "agent_name": agent_name,
            "room_name": room_name,
            "dispatch_id": dispatch.id ,
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
    
@router.post("/start-batch-call/{agent_id}")
async def start_batch_agent_calls(
    agent_id: str,
    background_tasks: BackgroundTasks,
    phone_numbers: list[str] = Body(..., embed=True)
):
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
                validate_custom_function(node.custom_function.code)

        vector_store_id = getattr(agent_config.global_settings, "vector_store_id", None)
        if vector_store_id and vector_store_id not in vector_stores:
            raise HTTPException(
                status_code=400,
                detail=f"Vector store ID '{vector_store_id}' is not loaded in memory. "
                       f"Please ensure it's created and loaded before running the agent."
            )

        results = []

        for phone_number in phone_numbers:
            room_name = f"room-{uuid.uuid4().hex[:6]}"
            agent_name = f"agent-{uuid.uuid4().hex[:6]}"
            dispatch = await create_agent_dispatch(agent_id=agent_id, phone_number=phone_number, agent_name=agent_name, room_name=room_name)

            task = asyncio.create_task(agent_run(agent_name=agent_name, agent_id=agent_id))

            agent_sessions[agent_id + "_" + phone_number] = {
                "active": True,
                "status": "connected",
                "room_name": room_name,
                "started_at": datetime.now().isoformat(),
                "task": task
            }

            results.append({
                "agent_id": agent_id,
                "agent_name": agent_name,
                "room_name": room_name,
                "dispatch_id": dispatch.id,
                "phone_number": phone_number
            })

        return {
            "status": "success",
            "total_calls": len(results),
            "calls": results
        }

    except ValidationError as ve:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid agent configuration: {ve.errors()}"
        )
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Unexpected error while starting batch agents: {str(e)}"
        )