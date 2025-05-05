from fastapi import WebSocket
from typing import Dict
import asyncio

class WebSocketManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, agent_id: str, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[agent_id] = websocket

    def disconnect(self, agent_id: str):
        if agent_id in self.active_connections:
            del self.active_connections[agent_id]

    async def send_node_update(self, agent_id: str, node_id: str):
        websocket = self.active_connections.get(agent_id)
        if websocket:
            try:
                await websocket.send_json({
                    "type": "node_switched",
                    "agent_id": agent_id,
                    "node_id": node_id
                })
            except Exception as e:
                print(f"Failed to send message: {e}")

ws_manager = WebSocketManager()