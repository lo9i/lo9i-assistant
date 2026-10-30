"""AssistantService: the only core API that gateways use.

The service is a facade (`service.py`) composed of mixins, one per concern:
threads, channel threads, files, the handed folder, memory, channels, email, mcp, sign-ins, alerts, doctor,
notifications, home, follow-ups, tasks, repositories, model, identity, prompts, speech, log level, language, web
search, skills, skill imports, pinned skills, jobs, usage, messaging, runs and locking.
"""

from assistant.core.agent.alerts import Alert, AlertArea
from assistant.core.agent.channels import ChannelNotConnectedError, ChannelStatus, SetupItem
from assistant.core.agent.conversations import Conversation, ShownCall, ShownMessage, ShownStep
from assistant.core.agent.devices import Device, DeviceError, PairingCode
from assistant.core.agent.doctor import Cause, ContextPart, DoctorPage, DoctorReport, KnownCause, StartingContext
from assistant.core.agent.email import EmailAccount, EmailAccountNotFoundError, EmailError, EmailProvider
from assistant.core.agent.files import FileUnavailableError, UploadedFile
from assistant.core.agent.handed_folder import (
    FileChange,
    FilePreview,
    FolderChanges,
    FolderContents,
    FolderEntry,
    HandedFolderError,
    MissingPathError,
    NotHandedError,
    OutsideFolderError,
)
from assistant.core.agent.handoffs import Agent, AgentFolders, FolderError, FolderListing, Handoff, HandoffError
from assistant.core.agent.home import HomeCard, HomeItem, HomePage, HomeSection, HomeSectionsError, SectionResult
from assistant.core.agent.identity import InvalidNameError
from assistant.core.agent.jobs import Job, JobError, RunRecord
from assistant.core.agent.language import Language, LanguageError
from assistant.core.agent.mcp import (
    McpProbe,
    McpServer,
    McpServerChanges,
    McpServerError,
    McpServerStatus,
    McpToolInfo,
    PluginIcon,
)
from assistant.core.agent.memory import Episode, Fact, MemoryEditError, MemoryNotFoundError
from assistant.core.agent.model import ModelOption, ModelProvider, ModelSettingsError, ModelStatus, ProviderField
from assistant.core.agent.notifications import Notification
from assistant.core.agent.prompts import PromptEditError, PromptSection, UnknownPromptError
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
from assistant.core.agent.skill_imports import Importable, Importables, ImportOutcome
from assistant.core.agent.skills import FoundSkill, Skill, SkillError, SkillSummary
from assistant.core.agent.snapshot import MemorySnapshot
from assistant.core.agent.speech import Decoding, SpeechSettingsError, SpeechStatus, SpokenReplies, SynthesisError
from assistant.core.agent.tasks import RunningTask
from assistant.core.agent.threads import ConversationBusyError, ConversationError
from assistant.core.agent.usage import ConversationStats, TokenReport, UsageReport
from assistant.core.agent.web_search import InvalidSearchKeyError, WebSearchStatus

__all__ = [
    "Agent",
    "AgentFolders",
    "Alert",
    "AlertArea",
    "AssistantService",
    "Cause",
    "ChannelNotConnectedError",
    "ChannelStatus",
    "ContextPart",
    "Conversation",
    "ConversationBusyError",
    "ConversationError",
    "ConversationStats",
    "Decoding",
    "Device",
    "DeviceError",
    "DoctorPage",
    "DoctorReport",
    "EmailAccount",
    "EmailAccountNotFoundError",
    "EmailError",
    "EmailProvider",
    "Episode",
    "Fact",
    "FileChange",
    "FilePreview",
    "FileUnavailableError",
    "FolderChanges",
    "FolderContents",
    "FolderEntry",
    "FolderError",
    "FolderListing",
    "FoundServer",
    "FoundSkill",
    "HandedFolderError",
    "Handoff",
    "HandoffError",
    "HomeCard",
    "HomeItem",
    "HomePage",
    "HomeSection",
    "HomeSectionsError",
    "ImportOutcome",
    "Importable",
    "Importables",
    "InstalledFromRepository",
    "InvalidNameError",
    "InvalidSearchKeyError",
    "Job",
    "JobError",
    "KeptKeys",
    "KnownCause",
    "Language",
    "LanguageError",
    "McpProbe",
    "McpServer",
    "McpServerChanges",
    "McpServerError",
    "McpServerStatus",
    "McpToolInfo",
    "MemoryEditError",
    "MemoryNotFoundError",
    "MemorySnapshot",
    "MissingPathError",
    "ModelOption",
    "ModelProvider",
    "ModelSettingsError",
    "ModelStatus",
    "NotHandedError",
    "Notification",
    "OutsideFolderError",
    "PairingCode",
    "PluginIcon",
    "PluginUpdate",
    "PromptEditError",
    "PromptSection",
    "ProviderField",
    "Repository",
    "RepositoryContents",
    "RepositoryError",
    "RepositoryPlugins",
    "RunRecord",
    "RunningTask",
    "SectionResult",
    "ServerField",
    "ServerValues",
    "Session",
    "SetupItem",
    "ShownCall",
    "ShownMessage",
    "ShownStep",
    "SignInError",
    "SignedIn",
    "Skill",
    "SkillError",
    "SkillSummary",
    "SpeechSettingsError",
    "SpeechStatus",
    "SpokenReplies",
    "StartingContext",
    "SynthesisError",
    "TokenReport",
    "UnknownPromptError",
    "UploadedFile",
    "UsageReport",
    "WebSearchStatus",
]
