import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    LIVEKIT_API_KEY: str = os.getenv("LIVEKIT_API_KEY")
    LIVEKIT_API_SECRET: str = os.getenv("LIVEKIT_API_SECRET")
    LIVEKIT_URL: str = os.getenv("LIVEKIT_URL")
    MONGODB_URI: str = os.getenv("MONGODB_URI")
    MONGODB_NAME: str = os.getenv("MONGODB_NAME")
    SIP_OUTBOUND_TRUNK_ID: str = os.getenv("SIP_OUTBOUND_TRUNK_ID", "default_trunk_id")

    if not all([LIVEKIT_API_KEY, LIVEKIT_API_SECRET, LIVEKIT_URL, MONGODB_URI, MONGODB_NAME]):
        raise Exception("Environment variables not set properly. Please check your .env file.") 

settings = Settings()
