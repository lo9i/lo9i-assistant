"""DaemonClient: the service's client-facing methods over the daemon's HTTP API.

The conversation (sessions, runs, events) comes from mixins on `DaemonClient` (`client.py`); the
other API routes are grouped in one small class per part of the daemon (`client.telegram`,
`client.email`, ...), in their own modules. `transport.py` holds the shared HTTP connection.
"""

from assistant.client.daemon_client.client import DaemonClient
from assistant.client.daemon_client.clients import ClientsApi
from assistant.client.daemon_client.conversations import ConversationsApi
from assistant.client.daemon_client.devices import DevicesApi
from assistant.client.daemon_client.email import EmailApi
from assistant.client.daemon_client.identity import IdentityApi
from assistant.client.daemon_client.jobs import JobsApi
from assistant.client.daemon_client.mcp import McpApi
from assistant.client.daemon_client.memory import MemoryApi
from assistant.client.daemon_client.skills import SkillsApi
from assistant.client.daemon_client.slack import SlackApi
from assistant.client.daemon_client.speech import SpeechApi
from assistant.client.daemon_client.system import SystemApi
from assistant.client.daemon_client.telegram import TelegramApi
from assistant.client.daemon_client.usage import UsageApi

__all__ = [
    "ClientsApi",
    "ConversationsApi",
    "DaemonClient",
    "DevicesApi",
    "EmailApi",
    "IdentityApi",
    "JobsApi",
    "McpApi",
    "MemoryApi",
    "SkillsApi",
    "SlackApi",
    "SpeechApi",
    "SystemApi",
    "TelegramApi",
    "UsageApi",
]
