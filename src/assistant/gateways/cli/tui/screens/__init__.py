"""Modal screens opened from the chat: setup (Telegram, email, start at boot), browsing (skills,
jobs, usage, connected clients), and approvals."""

from assistant.gateways.cli.tui.screens.approval import ApprovalScreen
from assistant.gateways.cli.tui.screens.confirm import ConfirmScreen
from assistant.gateways.cli.tui.screens.conversations import ConversationsScreen
from assistant.gateways.cli.tui.screens.devices import DevicesScreen
from assistant.gateways.cli.tui.screens.email import EmailScreen
from assistant.gateways.cli.tui.screens.jobs import JobsScreen
from assistant.gateways.cli.tui.screens.sessions import SessionsScreen
from assistant.gateways.cli.tui.screens.skills import SkillsScreen
from assistant.gateways.cli.tui.screens.startup import StartupScreen
from assistant.gateways.cli.tui.screens.telegram import TelegramScreen
from assistant.gateways.cli.tui.screens.usage import UsageScreen

__all__ = [
    "ApprovalScreen",
    "ConfirmScreen",
    "ConversationsScreen",
    "DevicesScreen",
    "EmailScreen",
    "JobsScreen",
    "SessionsScreen",
    "SkillsScreen",
    "StartupScreen",
    "TelegramScreen",
    "UsageScreen",
]
