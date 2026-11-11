"""DaemonClient: the service's client-facing methods over the daemon's HTTP API.

The conversation (sessions, runs, events) comes from mixins on `DaemonClient` (`client.py`); the
other API routes are grouped in one small class per part of the daemon (`client.channels`,
`client.email`, ...), in their own modules. `transport.py` holds the shared HTTP connection.
"""

from lo9i.client.daemon_client.alerts import AlertsApi
from lo9i.client.daemon_client.channels import ChannelsApi
from lo9i.client.daemon_client.client import DaemonClient
from lo9i.client.daemon_client.clients import ClientsApi
from lo9i.client.daemon_client.conversations import ConversationsApi
from lo9i.client.daemon_client.devices import DevicesApi
from lo9i.client.daemon_client.doctor import DoctorApi
from lo9i.client.daemon_client.email import EmailApi
from lo9i.client.daemon_client.files import FilesApi
from lo9i.client.daemon_client.folders import FoldersApi, ShownFolder
from lo9i.client.daemon_client.home import HomeApi
from lo9i.client.daemon_client.identity import IdentityApi
from lo9i.client.daemon_client.jobs import JobsApi
from lo9i.client.daemon_client.logs import LogsApi
from lo9i.client.daemon_client.mcp import McpApi
from lo9i.client.daemon_client.memory import MemoryApi
from lo9i.client.daemon_client.migration import MigrationApi
from lo9i.client.daemon_client.model import ModelApi
from lo9i.client.daemon_client.notifications import NotificationsApi
from lo9i.client.daemon_client.oauth import OAuthApi
from lo9i.client.daemon_client.proactive import ProactiveApi
from lo9i.client.daemon_client.prompts import PromptsApi
from lo9i.client.daemon_client.repositories import RepositoriesApi, offered_plugin
from lo9i.client.daemon_client.setup_check import OlderDaemonError, SetupCheckApi
from lo9i.client.daemon_client.skills import SkillsApi
from lo9i.client.daemon_client.speech import SpeechApi
from lo9i.client.daemon_client.subagents import SubagentsApi
from lo9i.client.daemon_client.system import SystemApi
from lo9i.client.daemon_client.tasks import TasksApi
from lo9i.client.daemon_client.usage import UsageApi
from lo9i.client.daemon_client.voice_calls import VoiceCallsApi
from lo9i.client.daemon_client.web_search import WebSearchApi

__all__ = [
    "AlertsApi",
    "ChannelsApi",
    "ClientsApi",
    "ConversationsApi",
    "DaemonClient",
    "DevicesApi",
    "DoctorApi",
    "EmailApi",
    "FilesApi",
    "FoldersApi",
    "HomeApi",
    "IdentityApi",
    "JobsApi",
    "LogsApi",
    "McpApi",
    "MemoryApi",
    "MigrationApi",
    "ModelApi",
    "NotificationsApi",
    "OAuthApi",
    "OlderDaemonError",
    "ProactiveApi",
    "PromptsApi",
    "RepositoriesApi",
    "SetupCheckApi",
    "ShownFolder",
    "SkillsApi",
    "SpeechApi",
    "SubagentsApi",
    "SystemApi",
    "TasksApi",
    "UsageApi",
    "VoiceCallsApi",
    "WebSearchApi",
    "offered_plugin",
]
