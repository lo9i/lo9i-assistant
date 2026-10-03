"""Modal screens opened from the chat: setup (the model, audio, web search, Telegram, Slack, email, MCP servers,
start at boot), browsing (plugins, skills, jobs, files, usage, connected clients), the profile, approvals and
questions."""

from assistant_terminal.tui.screens.approval import ApprovalScreen
from assistant_terminal.tui.screens.audio import AudioScreen
from assistant_terminal.tui.screens.confirm import ConfirmScreen
from assistant_terminal.tui.screens.conversations import ConversationsScreen
from assistant_terminal.tui.screens.devices import DevicesScreen
from assistant_terminal.tui.screens.email import EmailScreen
from assistant_terminal.tui.screens.files import FilesScreen
from assistant_terminal.tui.screens.jobs import JobsScreen
from assistant_terminal.tui.screens.mcp import McpScreen
from assistant_terminal.tui.screens.model import ModelScreen
from assistant_terminal.tui.screens.plugins import PluginsScreen
from assistant_terminal.tui.screens.profile import ProfileScreen
from assistant_terminal.tui.screens.question import QuestionScreen
from assistant_terminal.tui.screens.sessions import SessionsScreen
from assistant_terminal.tui.screens.skills import SkillsScreen
from assistant_terminal.tui.screens.slack import SlackScreen
from assistant_terminal.tui.screens.startup import StartupScreen
from assistant_terminal.tui.screens.telegram import TelegramScreen
from assistant_terminal.tui.screens.usage import UsageScreen
from assistant_terminal.tui.screens.web_search import WebSearchScreen

__all__ = [
    "ApprovalScreen",
    "AudioScreen",
    "ConfirmScreen",
    "ConversationsScreen",
    "DevicesScreen",
    "EmailScreen",
    "FilesScreen",
    "JobsScreen",
    "McpScreen",
    "ModelScreen",
    "PluginsScreen",
    "ProfileScreen",
    "QuestionScreen",
    "SessionsScreen",
    "SkillsScreen",
    "SlackScreen",
    "StartupScreen",
    "TelegramScreen",
    "UsageScreen",
    "WebSearchScreen",
]
