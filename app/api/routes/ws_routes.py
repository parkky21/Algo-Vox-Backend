from fastapi import WebSocket
from app.core.ws_manager import ws_manager

async def agent_ws(websocket: WebSocket, agent_id: str):
    await ws_manager.connect(agent_id, websocket)
    try:
        while True:
            await websocket.receive_text()  # Keep connection open
    except Exception:
        pass
    finally:
        ws_manager.disconnect(agent_id)
