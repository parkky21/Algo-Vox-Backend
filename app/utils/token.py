# server.py
import datetime
from livekit import api

LIVEKIT_API_KEY="APIYzqLsmBChBFz"
LIVEKIT_API_SECRET="eVTStfVzKiQ1lTzVWxebpxzCKM5M6JFCesXJdJXZb4OA"


def get_token(agent:str, identity:str,room:str):
    token = (
        api.AccessToken(
            api_key=LIVEKIT_API_KEY,
            api_secret=LIVEKIT_API_SECRET
        )
        .with_identity(identity)
        # .with_ttl(datetime.timedelta(minutes=10))
        .with_grants(api.VideoGrants(room_join=True, room=room))
        .with_room_config(
            api.RoomConfiguration(
                agents=[api.RoomAgentDispatch(agent_name=agent)]
            )
        )
        .to_jwt()
    )

    return token



# from livekit.api import CreateRoomRequest

# room = await lkapi.room.create_room(CreateRoomRequest(
#   name="myroom",
#   empty_timeout=10 * 60,
#   max_participants=20,
# ))

# from livekit.api import DeleteRoomRequest

# await lkapi.room.delete_room(DeleteRoomRequest(
#   room="myroom",
# ))