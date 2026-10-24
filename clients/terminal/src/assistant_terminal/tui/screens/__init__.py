"""Modal screens opened from the chat: setup (the model, audio, web search, chat channels, email, MCP
servers, start at boot), browsing (plugins, skills, jobs, files, usage, the daemon's log, connected
clients, notifications), the profile, the system prompt texts, approvals, questions and the folder an agent works in."""

from assistant_terminal.tui.screens.agent_folder import AgentFolderScreen
from assistant_terminal.tui.screens.approval import ApprovalScreen
from assistant_terminal.tui.screens.audio import AudioScreen
from assistant_terminal.tui.screens.channel_setup import ChannelSetupScreen
from assistant_terminal.tui.screens.confirm import ConfirmScreen
from assistant_terminal.tui.screens.conversations import ConversationsScreen
from assistant_terminal.tui.screens.devices import DevicesScreen
from assistant_terminal.tui.screens.email import EmailScreen
from assistant_terminal.tui.screens.email_recipients import EmailRecipientsScreen
from assistant_terminal.tui.screens.files import FilesScreen
from assistant_terminal.tui.screens.home import HomeScreen
from assistant_terminal.tui.screens.host import HostScreen
from assistant_terminal.tui.screens.jobs import JobsScreen
from assistant_terminal.tui.screens.kept_keys_list import KeptKeysListScreen
from assistant_terminal.tui.screens.logs import LogsScreen
from assistant_terminal.tui.screens.mcp import McpScreen
from assistant_terminal.tui.screens.model import ModelScreen
from assistant_terminal.tui.screens.notifications import NotificationsScreen
from assistant_terminal.tui.screens.plugins import PluginsScreen
from assistant_terminal.tui.screens.profile import ProfileScreen
from assistant_terminal.tui.screens.prompts import PromptsScreen
from assistant_terminal.tui.screens.question import QuestionScreen
from assistant_terminal.tui.screens.repository_install import RepositoryInstallScreen
from assistant_terminal.tui.screens.sessions import SessionsScreen
from assistant_terminal.tui.screens.skills import SkillsScreen
from assistant_terminal.tui.screens.startup import StartupScreen
from assistant_terminal.tui.screens.usage import UsageScreen
from assistant_terminal.tui.screens.web_search import WebSearchScreen

__all__ = [
    "AgentFolderScreen",
    "ApprovalScreen",
    "AudioScreen",
    "ChannelSetupScreen",
    "ConfirmScreen",
    "ConversationsScreen",
    "DevicesScreen",
    "EmailRecipientsScreen",
    "EmailScreen",
    "FilesScreen",
    "HomeScreen",
    "HostScreen",
    "JobsScreen",
    "KeptKeysListScreen",
    "LogsScreen",
    "McpScreen",
    "ModelScreen",
    "NotificationsScreen",
    "PluginsScreen",
    "ProfileScreen",
    "PromptsScreen",
    "QuestionScreen",
    "RepositoryInstallScreen",
    "SessionsScreen",
    "SkillsScreen",
    "StartupScreen",
    "UsageScreen",
    "WebSearchScreen",
]
