from fastapi import WebSocket
from typing import Dict, Set
import asyncio
import logging
import time
from app.utils.token import verify_ws_token  # Import your token verification function

# Set up logger
logger = logging.getLogger(__name__)

class WebSocketManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.connection_times: Dict[str, float] = {}  # Track when connections were established
        self.ip_connections: Dict[str, Set[str]] = {}  # Track connections per IP
        
    async def connect(self, agent_id: str, websocket: WebSocket, token: str = None):
        """
        Connect a WebSocket to an agent, with optional token verification
        
        Args:
            agent_id: The agent ID to connect to
            websocket: The WebSocket connection
            token: Optional token for verification
        """
        # Token verification (if enabled)
        if token is not None:
            if not verify_ws_token(token, agent_id):
                await websocket.close(code=4003, reason="Invalid token")
                logger.warning(f"Rejected WebSocket connection for agent {agent_id}: Invalid token")
                return False
        
        # Rate limiting by IP (optional)
        client_ip = websocket.client.host
        if client_ip in self.ip_connections and len(self.ip_connections[client_ip]) >= 5:  # Max 5 connections per IP
            await websocket.close(code=4029, reason="Too many connections")
            logger.warning(f"Rejected WebSocket connection from IP {client_ip}: Too many connections")
            return False
            
        try:
            # Accept the connection
            await websocket.accept()
            
            # Store the connection
            self.active_connections[agent_id] = websocket
            self.connection_times[agent_id] = time.time()
            
            # Track IP
            if client_ip not in self.ip_connections:
                self.ip_connections[client_ip] = set()
            self.ip_connections[client_ip].add(agent_id)
            
            logger.info(f"WebSocket connected for agent {agent_id} from IP {client_ip}")
            return True
            
        except Exception as e:
            logger.error(f"Error accepting WebSocket connection: {e}")
            return False

    def disconnect(self, agent_id: str):
        """
        Disconnect a WebSocket from an agent
        
        Args:
            agent_id: The agent ID to disconnect
        """
        if agent_id in self.active_connections:
            # Clean up IP tracking
            websocket = self.active_connections[agent_id]
            try:
                client_ip = websocket.client.host
                if client_ip in self.ip_connections:
                    self.ip_connections[client_ip].discard(agent_id)
                    if not self.ip_connections[client_ip]:  # Remove empty sets
                        del self.ip_connections[client_ip]
            except Exception:
                pass  # Connection might already be closed
                
            # Remove from tracking collections
            self.connection_times.pop(agent_id, None)
            del self.active_connections[agent_id]
            logger.info(f"WebSocket disconnected for agent {agent_id}")

    async def send_node_update(self, agent_id: str, node_id: str):
        """
        Send a node update notification to a connected client
        
        Args:
            agent_id: The agent ID to send to
            node_id: The node ID that was switched to
        """
        websocket = self.active_connections.get(agent_id)
        if websocket:
            try:
                await websocket.send_json({
                    "type": "node_switched",
                    "agent_id": agent_id,
                    "node_id": node_id,
                    "timestamp": time.time()
                })
                logger.debug(f"Sent node update to agent {agent_id}: {node_id}")
            except Exception as e:
                logger.error(f"Failed to send node update: {e}")
                # Optionally auto-disconnect on send failure
                # self.disconnect(agent_id)
                
    async def broadcast(self, message: dict):
        """
        Broadcast a message to all connected clients
        
        Args:
            message: The message to broadcast
        """
        disconnected = []
        for agent_id, websocket in self.active_connections.items():
            try:
                await websocket.send_json(message)
            except Exception as e:
                logger.error(f"Failed to broadcast to {agent_id}: {e}")
                disconnected.append(agent_id)
                
        # Clean up any disconnected clients
        for agent_id in disconnected:
            self.disconnect(agent_id)
            
    async def cleanup_stale_connections(self, max_age_seconds: int = 3600):
        """
        Cleanup connections that haven't been used for a while
        
        Args:
            max_age_seconds: Maximum age of connections in seconds
        """
        now = time.time()
        to_disconnect = []
        
        for agent_id, connected_at in self.connection_times.items():
            if now - connected_at > max_age_seconds:
                to_disconnect.append(agent_id)
                
        for agent_id in to_disconnect:
            websocket = self.active_connections.get(agent_id)
            if websocket:
                try:
                    await websocket.close(code=4000, reason="Connection timed out")
                except Exception:
                    pass
            self.disconnect(agent_id)
            
        return len(to_disconnect)

ws_manager = WebSocketManager()