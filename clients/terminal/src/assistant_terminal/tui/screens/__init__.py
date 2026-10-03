"""Modal screens opened from the chat: setup (Telegram, Slack, email, MCP servers, start at boot), browsing (skills,
jobs, usage, connected clients), and approvals."""

from assistant_terminal.tui.screens.approval import ApprovalScreen
from assistant_terminal.tui.screens.confirm import ConfirmScreen
from assistant_terminal.tui.screens.conversations import ConversationsScreen
from assistant_terminal.tui.screens.devices import DevicesScreen
from assistant_terminal.tui.screens.email import EmailScreen
from assistant_terminal.tui.screens.jobs import JobsScreen
from assistant_terminal.tui.screens.mcp import McpScreen
from assistant_terminal.tui.screens.sessions import SessionsScreen
from assistant_terminal.tui.screens.skills import SkillsScreen
from assistant_terminal.tui.screens.slack import SlackScreen
from assistant_terminal.tui.screens.startup import StartupScreen
from assistant_terminal.tui.screens.telegram import TelegramScreen
from assistant_terminal.tui.screens.usage import UsageScreen

__all__ = [
    "ApprovalScreen",
    "ConfirmScreen",
    "ConversationsScreen",
    "DevicesScreen",
    "EmailScreen",
    "JobsScreen",
    "McpScreen",
    "SessionsScreen",
    "SkillsScreen",
    "SlackScreen",
    "StartupScreen",
    "TelegramScreen",
    "UsageScreen",
]
