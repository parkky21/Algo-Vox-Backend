import os
import json
import logging
from datetime import datetime
from livekit.agents import AgentSession

logger = logging.getLogger(__name__)

async def write_transcript_file(session: AgentSession, room_name: str):
    try:
        current_date = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = os.path.join(os.getcwd(), "transcripts")
        os.makedirs(output_dir, exist_ok=True)
        file_path = os.path.join(output_dir, f"transcript_{room_name}_{current_date}.json")

        with open(file_path, "w") as f:
            json.dump(session.history.to_dict(), f, indent=2)

        logger.info(f"Transcript saved at: {file_path}")
    except Exception as e:
        logger.error(f"Failed to write transcript: {e}")
