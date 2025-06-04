import logging
from typing import Optional
from datetime import datetime, timezone
from livekit.agents.voice import Agent
from livekit.agents.llm import function_tool
from app.utils.call_control_tools import end_call
from app.utils.query_tool import build_query_tool
from app.utils.silence_detection import SilenceDetector

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("SingleAgent")

# Timestamp for consistent instruction context
now = datetime.now(timezone.utc).strftime("%A, %B %d, %Y at %I:%M %p UTC")
current_time = f"The current date and time is {now}."

class SingleAgent(Agent):
    def __init__(
        self,
        prompt: str,
        vector_store_id: str,
        timeout_seconds: Optional[int] = None
    ):
        self._silence_detector = None
        self._timeout = timeout_seconds

        tools = [end_call]

        try:
            query_tool = build_query_tool(vector_store_id)
            tools.append(query_tool)
            logger.info(f"Loaded query_info tool for vector store: {vector_store_id}")
        except Exception as e:
            logger.error(f"Failed to load query_info tool: {e}")

        instructions = f"{prompt}\n\n{current_time}"

        super().__init__(
            instructions=instructions,
            tools=tools,
        )

    async def on_enter(self):
        await self.session.generate_reply()
        if self._timeout and self._timeout > 0:
            self._silence_detector = SilenceDetector(self.session, self._timeout)
            await self._silence_detector.start()

    async def on_exit(self):
        if self._silence_detector:
            await self._silence_detector.stop()
            self._silence_detector = None
