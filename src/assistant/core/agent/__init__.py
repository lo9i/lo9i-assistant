"""AssistantService: the only core API that gateways use.

The service is a facade (`service.py`) composed of mixins, one per concern:
threads, memory, telegram, slack, email, mcp, identity, speech, skills, jobs, usage, messaging, runs and locking.
"""

from assistant.core.agent.conversations import Conversation, ShownMessage
from assistant.core.agent.devices import Device, DeviceError, PairingCode
from assistant.core.agent.email import EmailError, EmailProvider, EmailStatus
from assistant.core.agent.identity import InvalidNameError
from assistant.core.agent.jobs import Job, JobError, RunRecord
from assistant.core.agent.mcp import McpServer, McpServerChanges, McpServerError, McpServerStatus, McpToolInfo
from assistant.core.agent.service import AssistantService
from assistant.core.agent.session import Session
from assistant.core.agent.skills import Skill, SkillError, SkillSummary
from assistant.core.agent.slack import SlackError, SlackStatus
from assistant.core.agent.snapshot import MemorySnapshot
from assistant.core.agent.speech import SpeechSettingsError, SpeechStatus, SpokenReplies, SynthesisError
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
    "McpServer",
    "McpServerChanges",
    "McpServerError",
    "McpServerStatus",
    "McpToolInfo",
    "MemorySnapshot",
    "PairingCode",
    "RunRecord",
    "Session",
    "ShownMessage",
    "Skill",
    "SkillError",
    "SkillSummary",
    "SlackError",
    "SlackStatus",
    "SpeechSettingsError",
    "SpeechStatus",
    "SpokenReplies",
    "SynthesisError",
    "TelegramStatus",
    "UsageReport",
]
