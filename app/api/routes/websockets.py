import asyncio
from fastapi import WebSocket, status
from app.core.ws_manager import ws_manager
from app.utils.token import verify_ws_token

async def agent_ws(websocket: WebSocket, agent_id: str):
    # Get the token from query parameters
    token = websocket.query_params.get("token")
    
    # Check if token exists
    if not token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Missing authentication token")
        return
    
    # Verify the token
    if not verify_ws_token(token, agent_id):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid authentication token")
        return
    
    # Token is valid, proceed with connection
    await ws_manager.connect(agent_id, websocket)
    try:
        while True:
            await websocket.receive_text()  # Keep connection open
    except Exception as e:
        print(f"WebSocket error: {e}")
    finally:
        ws_manager.disconnect(agent_id)