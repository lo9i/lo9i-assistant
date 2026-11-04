"""The app's pages (page.py), Settings and its sections, one per tab (settings.py, section.py), and the dialogs
opened from them and from the chat: setup (the model, audio, web search, chat channels, email, MCP servers, start
at boot), browsing (plugins, skills, jobs, files, usage, the daemon's log, connected clients, notifications, the
health check), the About you step, the profile, the system prompt texts, approvals, questions and the folder an
agent works in."""

from lo9i_terminal.tui.screens.about_you import AboutYouScreen, SuggestedPluginsScreen
from lo9i_terminal.tui.screens.agent_folder import AgentFolderScreen
from lo9i_terminal.tui.screens.alerts import AlertsScreen
from lo9i_terminal.tui.screens.approval import ApprovalScreen
from lo9i_terminal.tui.screens.audio import AudioSection
from lo9i_terminal.tui.screens.briefing import BriefingSection
from lo9i_terminal.tui.screens.channel_setup import ChannelSetupScreen
from lo9i_terminal.tui.screens.confirm import ConfirmScreen
from lo9i_terminal.tui.screens.conversations import ConversationsScreen
from lo9i_terminal.tui.screens.devices import DevicesScreen
from lo9i_terminal.tui.screens.doctor import DoctorSection
from lo9i_terminal.tui.screens.email import EmailScreen
from lo9i_terminal.tui.screens.email_recipients import EmailRecipientsSection
from lo9i_terminal.tui.screens.files import FilesScreen
from lo9i_terminal.tui.screens.folder import FolderScreen
from lo9i_terminal.tui.screens.form import FormScreen
from lo9i_terminal.tui.screens.home import HomeScreen
from lo9i_terminal.tui.screens.host import HostSection
from lo9i_terminal.tui.screens.jobs import JobsScreen
from lo9i_terminal.tui.screens.kept_keys_list import KeptKeysListSection
from lo9i_terminal.tui.screens.language import LanguageSection
from lo9i_terminal.tui.screens.logs import LogsSection
from lo9i_terminal.tui.screens.mcp import McpSection
from lo9i_terminal.tui.screens.model import ModelSection
from lo9i_terminal.tui.screens.notifications import NotificationsScreen
from lo9i_terminal.tui.screens.open_conversations import OpenConversationsScreen
from lo9i_terminal.tui.screens.plugin_settings import PluginSettingsScreen
from lo9i_terminal.tui.screens.plugin_sign_in import PluginSignInScreen
from lo9i_terminal.tui.screens.plugins import PluginsSection
from lo9i_terminal.tui.screens.profile import ProfileSection
from lo9i_terminal.tui.screens.prompts import PromptsSection
from lo9i_terminal.tui.screens.question import QuestionScreen
from lo9i_terminal.tui.screens.repository_install import RepositoryInstallScreen
from lo9i_terminal.tui.screens.sessions import SessionsSection
from lo9i_terminal.tui.screens.settings import SettingsScreen
from lo9i_terminal.tui.screens.skill_imports import SkillImportsScreen
from lo9i_terminal.tui.screens.skills import SkillsSection
from lo9i_terminal.tui.screens.spending import SpendingLimitsSection
from lo9i_terminal.tui.screens.startup import StartupSection
from lo9i_terminal.tui.screens.subagents import SubagentsScreen
from lo9i_terminal.tui.screens.usage import UsageScreen
from lo9i_terminal.tui.screens.web_search import WebSearchSection

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
