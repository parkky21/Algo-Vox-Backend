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
from app.core.single_agent import SingleAgent
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
        agent_config = parse_agent_config(flow)

        # Build model instances
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

        # Create AgentSession
        session = AgentSession(
            stt=stt,
            llm=llm,
            tts=tts,
            vad=silero.VAD.load(
                min_speech_duration=0.1,
                min_silence_duration=0.2,
                prefix_padding_duration=0.05,
                max_buffered_speech=5.0,
                activation_threshold=0.5,
                sample_rate=16000,
                force_cpu=True
            )
        )

        print(agent_config.flow_type)

        ctx.add_shutdown_callback(lambda: write_transcript_file(session, ctx.room.name))

        # Choose agent based on flow_type
        if getattr(agent_config, "flow_type", "") == "single-prompt":
            logger.info("Launching Single Prompt Agent")
            vector_store_id = agent_config.global_settings.vector_store_id
            prompt = agent_config.global_settings.global_prompt or "How can I assist you?"
            timeout = agent_config.global_settings.timeout_seconds or 15

            agent = SingleAgent(
                prompt=prompt,
                vector_store_id=vector_store_id,
                timeout_seconds=timeout
            )
        else:
            logger.info("Launching Multi-Flow Agent")
            entry_node = agent_config.entry_node
            if not entry_node:
                logger.error(f"No entry node defined in agent config for ID: {agent_id}")
                return
            agent = await create_agent(entry_node, agent_config=agent_config, agent_id=agent_id)

        # Start agent session
        session_started = asyncio.create_task(session.start(agent=agent, room=ctx.room))

        # Optional background audio
        bg_audio_cfg = agent_config.global_settings.background_audio
        if bg_audio_cfg and bg_audio_cfg.enabled:
            try:
                background_audio = BackgroundAudioPlayer(
                    ambient_sound=AudioConfig(
                        BuiltinAudioClip.OFFICE_AMBIENCE,
                        volume=bg_audio_cfg.ambient_volume
                    ),
                    thinking_sound=[
                        AudioConfig(BuiltinAudioClip.KEYBOARD_TYPING, volume=bg_audio_cfg.thinking_volume),
                        AudioConfig(BuiltinAudioClip.KEYBOARD_TYPING2, volume=bg_audio_cfg.thinking_volume),
                    ]
                )
                await background_audio.start(room=ctx.room, agent_session=session)
                logger.info("Background audio started.")
            except Exception as e:
                logger.error(f"Error applying background audio config: {e}")

        # SIP Integration (if applicable)
        if "phone_number" in metadata:
            participant_identity = metadata["phone_number"]
            logger.info(f"Dialing SIP participant: {participant_identity}")
            await ctx.api.sip.create_sip_participant(
                api.CreateSIPParticipantRequest(
                    room_name=ctx.room.name,
                    sip_trunk_id=settings.SIP_OUTBOUND_TRUNK_ID,
                    sip_call_to=participant_identity,
                    participant_identity=participant_identity,
                    wait_until_answered=True,
                )
            )
            await session_started
            participant = await ctx.wait_for_participant(identity=participant_identity)
            logger.info(f"Participant joined: {participant.identity}")
        else:
            await session_started

    except api.TwirpError as e:
        logger.error(
            f"SIP participant error: {e.message} | SIP status: {e.metadata.get('sip_status_code')} {e.metadata.get('sip_status')}"
        )
        ctx.shutdown()

    except Exception as e:
        logger.exception(f"Unexpected error in entrypoint: {e}")
