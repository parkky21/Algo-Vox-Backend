from livekit.agents import function_tool, RunContext
from livekit.api import DeleteRoomRequest
from livekit.agents import get_job_context
import logging
import aiohttp

logger = logging.getLogger("end-call")

@function_tool()
async def end_call(context: RunContext) -> dict:
    """
    Only Use this tool to if you want to end the call.
    """
    try:
        # await context.session.generate_reply(instructions="Thank the user for their time")
        job_ctx = get_job_context()

        room_name = job_ctx.room.name
        logger.info(f"Attempting to delete room: {room_name}")

        await job_ctx.api.room.delete_room(DeleteRoomRequest(room=room_name))
        logger.info(f"Room '{room_name}' deleted successfully.")

        return {
            "status": "success",
            "message": f"Call ended and room '{room_name}' deleted."
        }

    except aiohttp.ClientError as e:
        logger.warning(f"Network error while deleting room: {e}")
        return {
            "status": "warning",
            "message": "Call ended, but room deletion may have failed due to network issue.",
            "error": str(e)
        }

    except Exception as e:
        logger.error(f"Unexpected error in end_call tool: {e}")
        return {
            "status": "error",
            "message": "Failed to end the call gracefully.",
            "error": str(e)
        }
