"""AssistantService: the only core API that gateways use.

The service is a facade (`service.py`) composed of mixins, one per concern:
threads, memory, channels, email, mcp, sign-ins, alerts, repositories, model, identity, speech, web search,
skills, jobs, usage, messaging, runs and locking.
"""

from assistant.core.agent.alerts import Alert
from assistant.core.agent.channels import ChannelNotConnectedError, ChannelStatus, SetupItem
from assistant.core.agent.conversations import Conversation, ShownMessage
from assistant.core.agent.devices import Device, DeviceError, PairingCode
from assistant.core.agent.email import EmailAccount, EmailAccountNotFoundError, EmailError, EmailProvider
from assistant.core.agent.identity import InvalidNameError
from assistant.core.agent.jobs import Job, JobError, RunRecord
from assistant.core.agent.mcp import (
    McpProbe,
    McpServer,
    McpServerChanges,
    McpServerError,
    McpServerStatus,
    McpToolInfo,
)
from assistant.core.agent.model import ModelProvider, ModelSettingsError, ModelStatus, ProviderField
from assistant.core.agent.repositories import (
    FoundServer,
    InstalledFromRepository,
    PluginUpdate,
    RepositoryContents,
    RepositoryError,
    ServerField,
    ServerValues,
)
from assistant.core.agent.service import AssistantService
from assistant.core.agent.session import Session
from assistant.core.agent.sign_ins import SignedIn, SignInError
from assistant.core.agent.skills import FoundSkill, Skill, SkillError, SkillSummary
from assistant.core.agent.snapshot import MemorySnapshot
from assistant.core.agent.speech import Decoding, SpeechSettingsError, SpeechStatus, SpokenReplies, SynthesisError
from assistant.core.agent.threads import ConversationBusyError, ConversationError
from assistant.core.agent.usage import TokenReport, UsageReport
from assistant.core.agent.web_search import InvalidSearchKeyError, WebSearchStatus

__all__ = [
    "Alert",
    "AssistantService",
    "ChannelNotConnectedError",
    "ChannelStatus",
    "Conversation",
    "ConversationBusyError",
    "ConversationError",
    "Decoding",
    "Device",
    "DeviceError",
    "EmailAccount",
    "EmailAccountNotFoundError",
    "EmailError",
    "EmailProvider",
    "FoundServer",
    "FoundSkill",
    "InstalledFromRepository",
    "InvalidNameError",
    "InvalidSearchKeyError",
    "Job",
    "JobError",
    "McpProbe",
    "McpServer",
    "McpServerChanges",
    "McpServerError",
    "McpServerStatus",
    "McpToolInfo",
    "MemorySnapshot",
    "ModelProvider",
    "ModelSettingsError",
    "ModelStatus",
    "PairingCode",
    "PluginUpdate",
    "ProviderField",
    "RepositoryContents",
    "RepositoryError",
    "RunRecord",
    "ServerField",
    "ServerValues",
    "Session",
    "SetupItem",
    "ShownMessage",
    "SignInError",
    "SignedIn",
    "Skill",
    "SkillError",
    "SkillSummary",
    "SpeechSettingsError",
    "SpeechStatus",
    "SpokenReplies",
    "SynthesisError",
    "TokenReport",
    "UsageReport",
    "WebSearchStatus",
]
