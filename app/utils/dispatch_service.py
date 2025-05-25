import asyncio
import json
from typing import Optional, Dict, Any
from livekit import api
from app.core.config import settings

async def create_agent_dispatch(
    agent_id: str,
    phone_number: str,
    agent_name: str = "outbound-caller",
    metadata: Optional[Dict[str, Any]] = None,
    room_name: str = "outbound",
) -> Optional[api.AgentDispatch]:
    """
    Create an agent dispatch for outbound calling.
    
    Args:
        phone_number: The phone number to call (e.g., "+918108709605")
        agent_name: Name of the agent to dispatch (default: "outbound-caller")
        metadata: Additional metadata to pass to the agent. If None, only phone_number is included.
        room_prefix: Prefix for the generated room name (default: "outbound")

    Returns:
        AgentDispatch object if successful, None if failed
        
    Raises:
        ValueError: If required environment variables are missing
    """
    # Use provided values or fall back to environment variables

    # Prepare metadata
    if metadata is None:
        metadata = {"phone_number": phone_number, "agent_id": agent_id}
       
    else:
        # Ensure phone_number is in metadata
        metadata["phone_number"] = phone_number
        metadata["agent_id"]= agent_id
    
    
    # Create API client
    lkapi = api.LiveKitAPI(url=settings.LIVEKIT_URL, api_key=settings.LIVEKIT_API_KEY, api_secret=settings.LIVEKIT_API_SECRET)
    
    try:
        request = api.CreateAgentDispatchRequest(
            agent_name=agent_name,
            metadata=json.dumps(metadata),
            room=room_name,
        )
        
        # Create the dispatch
        dispatch = await lkapi.agent_dispatch.create_dispatch(request)
        return dispatch
        
    except Exception as e:
        print(f" Error creating dispatch for {phone_number}: {e}")
        return None
        
    finally:
        # Always close the API client
        await lkapi.aclose()


async def create_multiple_dispatches(phone_numbers: list[str], **kwargs) -> list[Optional[api.AgentDispatch]]:
    """
    Create multiple agent dispatches for a list of phone numbers.
    
    Args:
        phone_numbers: List of phone numbers to call
        **kwargs: Additional arguments to pass to create_agent_dispatch
        
    Returns:
        List of AgentDispatch objects (None for failed dispatches)
    """
    tasks = [create_agent_dispatch(phone, **kwargs) for phone in phone_numbers]
    return await asyncio.gather(*tasks, return_exceptions=False)

