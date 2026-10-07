"""AssistantService: the only core API that gateways use.

The service is a facade (`service.py`) composed of mixins, one per concern:
threads, files, memory, channels, email, mcp, sign-ins, alerts, repositories, model, identity, speech,
web search, skills, pinned skills, jobs, usage, messaging, runs and locking.
"""

from assistant.core.agent.alerts import Alert
from assistant.core.agent.channels import ChannelNotConnectedError, ChannelStatus, SetupItem
from assistant.core.agent.conversations import Conversation, ShownMessage
from assistant.core.agent.devices import Device, DeviceError, PairingCode
from assistant.core.agent.email import EmailAccount, EmailAccountNotFoundError, EmailError, EmailProvider
from assistant.core.agent.files import FileUnavailableError, UploadedFile
from assistant.core.agent.handoffs import Agent, AgentFolders, FolderError, FolderListing, Handoff, HandoffError
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
from assistant.core.agent.memory import Episode, Fact, MemoryEditError, MemoryNotFoundError
from assistant.core.agent.model import ModelOption, ModelProvider, ModelSettingsError, ModelStatus, ProviderField
from assistant.core.agent.repositories import (
    FoundServer,
    InstalledFromRepository,
    KeptKeys,
    PluginUpdate,
    Repository,
    RepositoryContents,
    RepositoryError,
    RepositoryPlugins,
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
    "Agent",
    "AgentFolders",
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
    "Episode",
    "Fact",
    "FileUnavailableError",
    "FolderError",
    "FolderListing",
    "FoundServer",
    "FoundSkill",
    "Handoff",
    "HandoffError",
    "InstalledFromRepository",
    "InvalidNameError",
    "InvalidSearchKeyError",
    "Job",
    "JobError",
    "KeptKeys",
    "McpProbe",
    "McpServer",
    "McpServerChanges",
    "McpServerError",
    "McpServerStatus",
    "McpToolInfo",
    "MemoryEditError",
    "MemoryNotFoundError",
    "MemorySnapshot",
    "ModelOption",
    "ModelProvider",
    "ModelSettingsError",
    "ModelStatus",
    "PairingCode",
    "PluginUpdate",
    "ProviderField",
    "Repository",
    "RepositoryContents",
    "RepositoryError",
    "RepositoryPlugins",
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
    "UploadedFile",
    "UsageReport",
    "WebSearchStatus",
]
