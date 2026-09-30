"""AssistantService: the only core API that gateways use.

The service is a facade (`service.py`) composed of mixins, one per concern:
threads, memory, telegram, messaging, runs and locking.
"""

from assistant.core.agent.service import AssistantService
from assistant.core.agent.session import Session
from assistant.core.agent.snapshot import MemorySnapshot
from assistant.core.agent.telegram import InvalidToken, TelegramStatus

__all__ = ["AssistantService", "InvalidToken", "MemorySnapshot", "Session", "TelegramStatus"]
