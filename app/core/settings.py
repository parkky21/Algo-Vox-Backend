import os
from dotenv import load_dotenv

# Load from .env file (optional if you want local development support)
load_dotenv()

class Settings:
    LIVEKIT_API_KEY: str = os.getenv("LIVEKIT_API_KEY")
    LIVEKIT_API_SECRET: str = os.getenv("LIVEKIT_API_SECRET")
    LIVEKIT_URL: str = os.getenv("LIVEKIT_URL")

settings = Settings()
