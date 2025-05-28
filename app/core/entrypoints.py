import asyncio
import json
import logging
from livekit import api
from livekit.plugins import silero
from livekit.agents import AgentSession, JobContext,BackgroundAudioPlayer, AudioConfig, BuiltinAudioClip
from app.utils.agent_builder import build_llm_instance, build_stt_instance, build_tts_instance
from app.utils.node_parser import parse_agent_config
from app.utils.mongodb_client import MongoDBClient
from app.utils.transcript_fnc import write_transcript_file
from app.core.dynamic_agent import create_agent
from app.core.config import settings
# from livekit.plugins.turn_detector.english import EnglishModel

# from livekit.plugins import noise_cancellation
# from livekit.agents import RoomInputOptions

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("EntryPoint")

async def entrypoint(ctx: JobContext):
    try:
        logger.info(f"Connecting to room: {ctx.room.name}")
        await ctx.connect()

        metadata = json.loads(ctx.job.metadata)
        agent_id = metadata["agent_id"]

        mongo_client = MongoDBClient()

        flow = mongo_client.get_flow_by_id(agent_id)

        if not flow:
            logger.error(f"Agent config not found for ID: {agent_id}")
            return

        api_key = flow.get("global_settings", {}).get("tts", {}).get("api_key")
        if isinstance(api_key, dict):
            private_key = api_key.get("private_key")
            if private_key and "\\n" in private_key:
                api_key["private_key"] = private_key.replace("\\n", "\n")

        agent_config = parse_agent_config(flow)
        logger.info(f"Loaded agent config for ID: {agent_config}")
        if not agent_config.nodes or not agent_config.global_settings:
            logger.error(f"Incomplete agent config for ID: {agent_id}")
            return

        llm = build_llm_instance(
            agent_config.global_settings.llm.provider,
            agent_config.global_settings.llm.model,
            agent_config.global_settings.llm.api_key,
            agent_config.global_settings.temperature
        )
        stt = build_stt_instance(
            agent_config.global_settings.stt.provider,
            agent_config.global_settings.stt.model,
            agent_config.global_settings.stt.language,
            agent_config.global_settings.stt.api_key
        )
        tts = build_tts_instance(
            agent_config.global_settings.tts.provider,
            agent_config.global_settings.tts.model,
            agent_config.global_settings.tts.language,
            credentials_info=agent_config.global_settings.tts.api_key
        )

        session = AgentSession(
            stt=stt,
            llm=llm,
            tts=tts,
            vad=silero.VAD.load(),
            # turn_detection=EnglishModel(),

        )

        ctx.add_shutdown_callback(lambda: write_transcript_file(session, ctx.room.name))

        entry_node = agent_config.entry_node
        if not entry_node:
            logger.error(f"No entry node defined in agent config for ID: {agent_id}")
            return

        agent = await create_agent(entry_node, agent_config=agent_config, agent_id=agent_id)

        # Start the session before dialing (if telephony)
        session_started = asyncio.create_task(
            session.start(agent=agent, 
                          room=ctx.room
                          # room_input_options=RoomInputOptions(
                            #     noise_cancellation=noise_cancellation.BVCTelephony(),
                            # )
                )
        )

    #     background_audio = BackgroundAudioPlayer(
    #   # play office ambience sound looping in the background
    #         ambient_sound=AudioConfig(BuiltinAudioClip.OFFICE_AMBIENCE, volume=0.8),
    #         # play keyboard typing sound when the agent is thinking
    #         thinking_sound=[
    #                 AudioConfig(BuiltinAudioClip.KEYBOARD_TYPING, volume=0.2),
    #                 AudioConfig(BuiltinAudioClip.KEYBOARD_TYPING2, volume=0.2),
    #             ],
    #         )

    #     await background_audio.start(room=ctx.room, agent_session=session)

        # Telephony integration (conditional block)
        if "phone_number" in metadata:     
            participant_identity = metadata["phone_number"]
            logger.info(f"Dialing SIP participant: {participant_identity}")
            logger.info(f"Using SIP trunk ID: {settings.SIP_OUTBOUND_TRUNK_ID}")
            logger.info(f"Room name: {ctx.room.name}")
            await ctx.api.sip.create_sip_participant(
                api.CreateSIPParticipantRequest(
                    room_name=ctx.room.name,
                    sip_trunk_id=settings.SIP_OUTBOUND_TRUNK_ID,
                    sip_call_to=participant_identity,
                    participant_identity=participant_identity,
                    wait_until_answered=True
                )
            )
            await session_started
            participant = await ctx.wait_for_participant(identity=participant_identity)
            logger.info(f"Participant joined: {participant.identity}")
            # optionally attach to agent if needed: agent.set_participant(participant)
        else:
            # standard agent session, no SIP call
            await session_started

    except api.TwirpError as e:
        logger.error(
            f"SIP participant error: {e.message} | SIP status: {e.metadata.get('sip_status_code')} {e.metadata.get('sip_status')}"
        )
        ctx.shutdown()

    except Exception as e:
        logger.exception(f"Unexpected error in entrypoint: {e}")
