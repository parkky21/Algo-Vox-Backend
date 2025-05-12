# server.py
import datetime
from livekit import api
from app.core.settings import settings

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
