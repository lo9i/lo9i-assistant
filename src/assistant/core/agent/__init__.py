"""AssistantService: the only core API the daemon uses.

The service is a facade (`service.py`) composed of mixins, one per concern:
threads, channel threads, files, the handed folder, memory, the About you step, channels, email, mcp, sign-ins,
alerts, doctor, notifications, home, follow-ups, held runs, tasks, background subagents, repositories, model,
devices, passkeys, identity, prompts, speech, log level, language, web search, skills, skill imports, pinned skills,
jobs, usage, live voice calls, messaging, runs and locking.
"""

from assistant.core.agent.about_you import AboutYou, AboutYouStatus, Suggested
from assistant.core.agent.alerts import Alert, AlertArea
from assistant.core.agent.channels import ChannelNotConnectedError, ChannelStatus, SetupItem
from assistant.core.agent.conversations import Conversation, ShownCall, ShownMessage, ShownStep
from assistant.core.agent.devices import Device, DeviceError, PairingCode
from assistant.core.agent.doctor import Cause, ContextPart, DoctorPage, DoctorReport, KnownCause, StartingContext
from assistant.core.agent.email import EmailAccount, EmailAccountNotFoundError, EmailError, EmailProvider
from assistant.core.agent.files import FileUnavailableError, UploadedFile
from assistant.core.agent.handed_folder import (
    DeletingOffError,
    FileChange,
    FileDiff,
    FilePreview,
    FolderChanges,
    FolderContents,
    FolderEntry,
    FolderRefresh,
    HandedFolderError,
    ListedFolder,
    MissingPathError,
    NotHandedError,
    OutsideFolderError,
)
from assistant.core.agent.handoffs import Agent, AgentFolders, FolderError, FolderListing, Handoff, HandoffError
from assistant.core.agent.home import (
    HomeCard,
    HomeItem,
    HomePage,
    HomePinError,
    HomeSection,
    HomeSectionsError,
    SectionResult,
)
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
from assistant.core.agent.passkeys import Passkey, PasskeyError, Site
from assistant.core.agent.plugin_settings import PluginFieldValue, PluginSettings
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
from assistant.core.agent.subagents import (
    BackgroundStep,
    BackgroundSubagent,
    SubagentDetails,
    SubagentError,
    SubagentNotFoundError,
)
from assistant.core.agent.tasks import RunningTask
from assistant.core.agent.threads import ConversationBusyError, ConversationError
from assistant.core.agent.usage import ConversationStats, SpendingStatus, TokenReport, UsageReport
from assistant.core.agent.voice_calls import VoiceCallError, VoiceCallSettings, VoiceChoiceError, VoiceKeyError
from assistant.core.agent.web_search import InvalidSearchKeyError, WebSearchStatus

__all__ = [
    "AboutYou",
    "AboutYouStatus",
    "Agent",
    "AgentFolders",
    "Alert",
    "AlertArea",
    "AssistantService",
    "BackgroundStep",
    "BackgroundSubagent",
    "Cause",
    "ChannelNotConnectedError",
    "ChannelStatus",
    "ContextPart",
    "Conversation",
    "ConversationBusyError",
    "ConversationError",
    "ConversationStats",
    "Decoding",
    "DeletingOffError",
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
    "FileDiff",
    "FilePreview",
    "FileUnavailableError",
    "FolderChanges",
    "FolderContents",
    "FolderEntry",
    "FolderError",
    "FolderListing",
    "FolderRefresh",
    "FoundServer",
    "FoundSkill",
    "HandedFolderError",
    "Handoff",
    "HandoffError",
    "HomeCard",
    "HomeItem",
    "HomePage",
    "HomePinError",
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
    "ListedFolder",
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
    "Passkey",
    "PasskeyError",
    "PluginFieldValue",
    "PluginIcon",
    "PluginSettings",
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
    "Site",
    "Skill",
    "SkillError",
    "SkillSummary",
    "SpeechSettingsError",
    "SpeechStatus",
    "SpendingStatus",
    "SpokenReplies",
    "StartingContext",
    "SubagentDetails",
    "SubagentError",
    "SubagentNotFoundError",
    "Suggested",
    "SynthesisError",
    "TokenReport",
    "UnknownPromptError",
    "UploadedFile",
    "UsageReport",
    "VoiceCallError",
    "VoiceCallSettings",
    "VoiceChoiceError",
    "VoiceKeyError",
    "WebSearchStatus",
]
