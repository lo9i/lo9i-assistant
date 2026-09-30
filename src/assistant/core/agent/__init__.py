"""AssistantService: the only core API that gateways use.

The service is a facade (`service.py`) composed of mixins, one per concern:
threads, memory, telegram, email, identity, skills, jobs, usage, messaging, runs and locking.
"""

from assistant.core.agent.email import EmailError, EmailStatus
from assistant.core.agent.identity import InvalidNameError
from assistant.core.agent.jobs import Job, JobError, RunRecord
from assistant.core.agent.service import AssistantService
from assistant.core.agent.session import Session
from assistant.core.agent.skills import Skill, SkillError
from assistant.core.agent.snapshot import MemorySnapshot
from assistant.core.agent.telegram import InvalidTokenError, TelegramStatus
from assistant.core.agent.usage import UsageReport

__all__ = [
    "AssistantService",
    "EmailError",
    "EmailStatus",
    "InvalidNameError",
    "InvalidTokenError",
    "Job",
    "JobError",
    "MemorySnapshot",
    "RunRecord",
    "Session",
    "Skill",
    "SkillError",
    "TelegramStatus",
    "UsageReport",
]
