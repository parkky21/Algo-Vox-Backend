from livekit.agents import function_tool, RunContext, get_job_context
from livekit.api import DeleteRoomRequest
from livekit import api
import logging
import aiohttp
import json
from livekit import rtc

logger = logging.getLogger("call_control")

async def hangup():
    """Helper function to hang up the call by deleting the room"""
    try:
        job_ctx = get_job_context()
        room_name = job_ctx.room.name
        logger.info(f"Attempting to delete room: {room_name}")
        await job_ctx.api.room.delete_room(DeleteRoomRequest(room=room_name))
        logger.info(f"Room '{room_name}' deleted successfully.")
    except Exception as e:
        logger.error(f"Error while deleting room: {e}")
        raise

@function_tool()
async def end_call(ctx: RunContext) -> dict:
    """
    Called when the user wants to end the call.
    """
    try:
        await ctx.session.generate_reply(instructions="Thanks the user for their precious time.")
        
        current_speech = ctx.session.current_speech
        if current_speech:
            await current_speech.wait_for_playout()

        await hangup()

        return {
            "status": "success",
            "message": "Call ended and room deleted."
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

@function_tool()
async def detected_answering_machine(ctx: RunContext) -> str:
    """
    Called when the call reaches voicemail. Use this tool AFTER you hear the voicemail greeting.
    """
    logger.info("Detected answering machine. Ending call...")
    try:
        current_speech = ctx.session.current_speech
        if current_speech:
            await current_speech.wait_for_playout()

        await hangup()
        return "Voicemail detected. Call ended."

    except Exception as e:
        logger.error(f"Error ending call after voicemail detection: {e}")
        return "Voicemail detected, but failed to end call properly."

@function_tool()
async def transfer_call(ctx: RunContext, participant: rtc.RemoteParticipant):
    """Transfer the call to a human agent, called after confirming with the user"""
    dial_info = json.loads(ctx.job.metadata)
    transfer_to = dial_info["transfer_to"]
    if not transfer_to:
        return "cannot transfer call"

    logger.info(f"transferring call to {transfer_to}")

    await ctx.session.generate_reply(
        instructions="let the user know you'll be transferring them"
    )

    job_ctx = get_job_context()
    try:
        await job_ctx.api.sip.transfer_sip_participant(
            api.TransferSIPParticipantRequest(
                room_name=job_ctx.room.name,
                participant_identity=participant.identity,
                transfer_to=f"tel:{transfer_to}",
            )
        )

        logger.info(f"transferred call to {transfer_to}")
    except Exception as e:
        logger.error(f"error transferring call: {e}")
        await ctx.session.generate_reply(
            instructions="there was an error transferring the call."
        )
        await hangup()


@function_tool()
async def set_volume(ctx:RunContext ,volume: int):
    """Set the volume of the audio output.

    Args:
        volume (int): The volume level to set. Must be between 0 and 100.
    """
    ctx.volume = volume
