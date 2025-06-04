import asyncio
import time
import logging

logger = logging.getLogger(__name__)

class SilenceDetector:
    def __init__(self, session, initial_timeout=10, warning_timeout=5):
        self.session = session
        self.initial_timeout = initial_timeout  # Wait time before warning
        self.warning_timeout = warning_timeout  # Wait time after warning
        
        self._task = None
        self._listening_start = None
        self._warning_start = None
        self._warning_given = False
        self._lock = asyncio.Lock()

    async def start(self):
        """Start silence detection."""
        if self._task and not self._task.done():
            return
        
        logger.info(f"Starting silence detection ({self.initial_timeout}s + {self.warning_timeout}s warning)")
        self._task = asyncio.create_task(self._monitor())

    async def stop(self):
        """Stop silence detection."""
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        
        self._reset()
        logger.info("Silence detection stopped")

    def _reset(self):
        """Reset state."""
        self._listening_start = None
        self._warning_start = None
        self._warning_given = False

    def _get_states(self):
        """Get both agent and user states safely."""
        agent_state = getattr(self.session, '_agent_state', None)
        user_state = getattr(self.session, '_user_state', None)
        return agent_state, user_state

    async def _monitor(self):
        """Main monitoring loop."""
        try:
            while True:
                if getattr(self.session, "ended", False):
                    break
                
                agent_state, user_state = self._get_states()
                
                async with self._lock:
                    # Check if both are in listening state (true silence)
                    if agent_state == "listening" and user_state == "listening":
                        await self._handle_silence()
                    else:
                        # Any activity (agent speaking, user speaking, etc.) resets detection
                        if self._listening_start is not None:
                            logger.debug(f"Activity detected - agent: {agent_state}, user: {user_state} - resetting")
                            self._reset()
                
                await asyncio.sleep(0.5)
                
        except asyncio.CancelledError:
            pass

    async def _handle_silence(self):
        """Handle true silence when both agent and user are listening."""
        now = time.time()
        
        # Stage 1: Initial waiting period
        if not self._warning_given:
            # Start timer if not already started
            if self._listening_start is None:
                self._listening_start = now
                logger.debug(f"Started silence timer - both agent and user listening")
                return
            
            elapsed = now - self._listening_start
            
            # Check if initial timeout reached
            if elapsed >= self.initial_timeout:
                logger.info(f"Initial silence timeout reached after {elapsed:.1f}s - giving warning")
                self._warning_given = True
                await self._warn()
                # Start warning timer AFTER warning message is complete
                self._warning_start = time.time()
                logger.debug(f"Warning completed - starting {self.warning_timeout}s countdown")
        
        # Stage 2: Warning period (only check if warning message already played)
        elif self._warning_start is not None:
            warning_elapsed = now - self._warning_start
            
            # Check if warning timeout reached
            if warning_elapsed >= self.warning_timeout:
                total_elapsed = now - self._listening_start
                logger.info(f"Warning timeout reached after {warning_elapsed:.1f}s (total: {total_elapsed:.1f}s)")
                await self._timeout()

    async def _warn(self):
        """Give warning to user."""
        logger.info("Giving silence warning")
        await self.session.say(
            f"Hello? Please respond in the next {self.warning_timeout} seconds or I'll end the call."
        )

    async def _timeout(self):
        """Handle timeout."""
        logger.info("Silence timeout - ending call")
        await self.session.say(
            "I didn't hear anything. Ending the call now. Goodbye!",
            allow_interruptions=False
        )
        
        # Import and call hangup
        from app.utils.call_control_tools import hangup
        await hangup()
        
        # Stop monitoring
        if self._task:
            self._task.cancel()