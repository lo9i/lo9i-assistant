"""The app's pages (page.py), Settings and its sections, one per tab (settings.py, section.py), and the dialogs
opened from them and from the chat: setup (the model, audio, web search, chat channels, email, MCP servers, start
at boot), browsing (plugins, skills, jobs, files, usage, the daemon's log, connected clients, notifications, the
health check), the About you step, the profile, the system prompt texts, approvals, questions and the folder an
agent works in."""

from assistant_terminal.tui.screens.about_you import AboutYouScreen, SuggestedPluginsScreen
from assistant_terminal.tui.screens.agent_folder import AgentFolderScreen
from assistant_terminal.tui.screens.alerts import AlertsScreen
from assistant_terminal.tui.screens.approval import ApprovalScreen
from assistant_terminal.tui.screens.audio import AudioSection
from assistant_terminal.tui.screens.briefing import BriefingSection
from assistant_terminal.tui.screens.channel_setup import ChannelSetupScreen
from assistant_terminal.tui.screens.confirm import ConfirmScreen
from assistant_terminal.tui.screens.conversations import ConversationsScreen
from assistant_terminal.tui.screens.devices import DevicesScreen
from assistant_terminal.tui.screens.doctor import DoctorSection
from assistant_terminal.tui.screens.email import EmailScreen
from assistant_terminal.tui.screens.email_recipients import EmailRecipientsSection
from assistant_terminal.tui.screens.files import FilesScreen
from assistant_terminal.tui.screens.folder import FolderScreen
from assistant_terminal.tui.screens.form import FormScreen
from assistant_terminal.tui.screens.home import HomeScreen
from assistant_terminal.tui.screens.host import HostSection
from assistant_terminal.tui.screens.jobs import JobsScreen
from assistant_terminal.tui.screens.kept_keys_list import KeptKeysListSection
from assistant_terminal.tui.screens.language import LanguageSection
from assistant_terminal.tui.screens.logs import LogsSection
from assistant_terminal.tui.screens.mcp import McpSection
from assistant_terminal.tui.screens.model import ModelSection
from assistant_terminal.tui.screens.notifications import NotificationsScreen
from assistant_terminal.tui.screens.open_conversations import OpenConversationsScreen
from assistant_terminal.tui.screens.plugin_settings import PluginSettingsScreen
from assistant_terminal.tui.screens.plugin_sign_in import PluginSignInScreen
from assistant_terminal.tui.screens.plugins import PluginsSection
from assistant_terminal.tui.screens.profile import ProfileSection
from assistant_terminal.tui.screens.prompts import PromptsSection
from assistant_terminal.tui.screens.question import QuestionScreen
from assistant_terminal.tui.screens.repository_install import RepositoryInstallScreen
from assistant_terminal.tui.screens.sessions import SessionsSection
from assistant_terminal.tui.screens.settings import SettingsScreen
from assistant_terminal.tui.screens.skill_imports import SkillImportsScreen
from assistant_terminal.tui.screens.skills import SkillsSection
from assistant_terminal.tui.screens.spending import SpendingLimitsSection
from assistant_terminal.tui.screens.startup import StartupSection
from assistant_terminal.tui.screens.subagents import SubagentsScreen
from assistant_terminal.tui.screens.usage import UsageScreen
from assistant_terminal.tui.screens.web_search import WebSearchSection

__all__ = [
    "AboutYouScreen",
    "AgentFolderScreen",
    "AlertsScreen",
    "ApprovalScreen",
    "AudioSection",
    "BriefingSection",
    "ChannelSetupScreen",
    "ConfirmScreen",
    "ConversationsScreen",
    "DevicesScreen",
    "DoctorSection",
    "EmailRecipientsSection",
    "EmailScreen",
    "FilesScreen",
    "FolderScreen",
    "FormScreen",
    "HomeScreen",
    "HostSection",
    "JobsScreen",
    "KeptKeysListSection",
    "LanguageSection",
    "LogsSection",
    "McpSection",
    "ModelSection",
    "NotificationsScreen",
    "OpenConversationsScreen",
    "PluginSettingsScreen",
    "PluginSignInScreen",
    "PluginsSection",
    "ProfileSection",
    "PromptsSection",
    "QuestionScreen",
    "RepositoryInstallScreen",
    "SessionsSection",
    "SettingsScreen",
    "SkillImportsScreen",
    "SkillsSection",
    "SpendingLimitsSection",
    "StartupSection",
    "SubagentsScreen",
    "SuggestedPluginsScreen",
    "UsageScreen",
    "WebSearchSection",
]
