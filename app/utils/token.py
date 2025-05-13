# server.py
import datetime
from livekit import api
from app.core.settings import settings
import time
import jwt

LIVEKIT_API_KEY = settings.LIVEKIT_API_KEY
LIVEKIT_API_SECRET = settings.LIVEKIT_API_SECRET

def get_token(agent:str,agent_id:str, identity:str,room:str):
    token = (
        api.AccessToken(
            api_key=LIVEKIT_API_KEY,
            api_secret=LIVEKIT_API_SECRET
        )
        .with_identity(identity)
        # Optional: Enable TTL if needed
        # .with_ttl(datetime.timedelta(minutes=10))
        .with_grants(api.VideoGrants(room_join=True, room=room))
        .with_room_config(
            api.RoomConfiguration(
                agents=[
                    api.RoomAgentDispatch(
                        agent_name=agent,
                        metadata=f'{{"agent_id": "{agent_id}"}}'
                    )
                ],
            )
        )
        .to_jwt()
    )
    return token


# Add this function for WebSocket tokens
def generate_ws_token(agent_id: str, expires_in_seconds: int = 3600):
    """
    Generate a JWT token for WebSocket authentication
    
    Args:
        agent_id: The agent ID to authenticate for
        expires_in_seconds: Token expiration time in seconds
        
    Returns:
        Encoded JWT token
    """
    payload = {
        "agent_id": agent_id,
        "exp": int(time.time()) + expires_in_seconds,
        "iat": int(time.time())
    }
    
    # Use an existing secret or create a new one
    secret = settings.LIVEKIT_API_SECRET  # Reuse existing secret or create a new one
    
    return jwt.encode(payload, secret, algorithm="HS256")

# Add a verification function
def verify_ws_token(token: str, agent_id: str) -> bool:
    """
    Verify a WebSocket JWT token
    
    Args:
        token: The JWT token to verify
        agent_id: The agent ID to validate against
        
    Returns:
        True if token is valid, False otherwise
    """
    try:
        secret = settings.LIVEKIT_API_SECRET  # Same secret used for encoding
        payload = jwt.decode(token, secret, algorithms=["HS256"])
        
        # Check if agent_id matches and token is not expired
        return payload.get("agent_id") == agent_id
    except jwt.PyJWTError:
        return False