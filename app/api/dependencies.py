# In app/api/dependencies.py
from fastapi import WebSocket, status
from app.utils.token import verify_ws_token

async def validate_ws_token(websocket: WebSocket, agent_id: str):
    token = websocket.query_params.get("token")
    
    if not token or not verify_ws_token(token, agent_id):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid token")
        return None
        
    return agent_id