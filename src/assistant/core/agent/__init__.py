"""AssistantService: the only core API that gateways use.

The service is a facade (`service.py`) composed of mixins, one per concern:
threads, memory, telegram, email, identity, skills, jobs, usage, messaging, runs and locking.
"""

from assistant.core.agent.conversations import Conversation, ShownMessage
from assistant.core.agent.devices import Device, DeviceError, PairingCode
from assistant.core.agent.email import EmailError, EmailProvider, EmailStatus
from assistant.core.agent.identity import InvalidNameError
from assistant.core.agent.jobs import Job, JobError, RunRecord
from assistant.core.agent.service import AssistantService
from assistant.core.agent.session import Session
from assistant.core.agent.skills import Skill, SkillError, SkillSummary
from assistant.core.agent.snapshot import MemorySnapshot
from assistant.core.agent.telegram import InvalidTokenError, TelegramStatus
from assistant.core.agent.threads import ConversationError
from assistant.core.agent.usage import UsageReport

__all__ = [
    "AssistantService",
    "Conversation",
    "ConversationError",
    "Device",
    "DeviceError",
    "EmailError",
    "EmailProvider",
    "EmailStatus",
    "InvalidNameError",
    "InvalidTokenError",
    "Job",
    "JobError",
    "MemorySnapshot",
    "PairingCode",
    "RunRecord",
    "Session",
    "ShownMessage",
    "Skill",
    "SkillError",
    "SkillSummary",
    "TelegramStatus",
    "UsageReport",
]
