import httpx

from lo9i.client.daemon_client.alerts import AlertsApi
from lo9i.client.daemon_client.channels import ChannelsApi
from lo9i.client.daemon_client.clients import ClientsApi
from lo9i.client.daemon_client.conversations import ConversationsApi
from lo9i.client.daemon_client.devices import DevicesApi
from lo9i.client.daemon_client.doctor import DoctorApi
from lo9i.client.daemon_client.email import EmailApi
from lo9i.client.daemon_client.events import EventsMixin
from lo9i.client.daemon_client.files import FilesApi
from lo9i.client.daemon_client.folders import FoldersApi
from lo9i.client.daemon_client.home import HomeApi
from lo9i.client.daemon_client.identity import IdentityApi
from lo9i.client.daemon_client.jobs import JobsApi
from lo9i.client.daemon_client.language import LanguageApi
from lo9i.client.daemon_client.logs import LogsApi
from lo9i.client.daemon_client.mcp import McpApi
from lo9i.client.daemon_client.memory import MemoryApi
from lo9i.client.daemon_client.model import ModelApi
from lo9i.client.daemon_client.notifications import NotificationsApi
from lo9i.client.daemon_client.oauth import OAuthApi
from lo9i.client.daemon_client.proactive import ProactiveApi
from lo9i.client.daemon_client.prompts import PromptsApi
from lo9i.client.daemon_client.repositories import RepositoriesApi
from lo9i.client.daemon_client.runs import RunsMixin
from lo9i.client.daemon_client.sessions import SessionsMixin
from lo9i.client.daemon_client.skills import SkillsApi
from lo9i.client.daemon_client.speech import SpeechApi
from lo9i.client.daemon_client.subagents import SubagentsApi
from lo9i.client.daemon_client.system import SystemApi
from lo9i.client.daemon_client.tasks import TasksApi
from lo9i.client.daemon_client.transport import Transport
from lo9i.client.daemon_client.usage import UsageApi
from lo9i.client.daemon_client.voice_calls import VoiceCallsApi
from lo9i.client.daemon_client.web_search import WebSearchApi


class DaemonClient(SessionsMixin, RunsMixin, EventsMixin):
    """Everything a client can ask the daemon. The conversation (sessions, runs, events) is on the
    client itself; everything else is grouped by the part of the daemon it changes."""

    def __init__(self, http: httpx.AsyncClient) -> None:
        transport = Transport(http)
        super().__init__(transport)
        self.conversations = ConversationsApi(transport)
        self.files = FilesApi(transport)
        self.folders = FoldersApi(transport)
        self.identity = IdentityApi(transport)
        self.memory = MemoryApi(transport)
        self.skills = SkillsApi(transport)
        self.jobs = JobsApi(transport)
        self.usage = UsageApi(transport)
        self.channels = ChannelsApi(transport)
        self.speech = SpeechApi(transport)
        self.web_search = WebSearchApi(transport)
        self.voice_calls = VoiceCallsApi(transport)
        self.model = ModelApi(transport)
        self.email = EmailApi(transport)
        self.oauth = OAuthApi(transport)
        self.mcp = McpApi(transport)
        self.alerts = AlertsApi(transport)
        self.doctor = DoctorApi(transport)
        self.notifications = NotificationsApi(transport)
        self.prompts = PromptsApi(transport)
        self.home = HomeApi(transport)
        self.proactive = ProactiveApi(transport)
        self.tasks = TasksApi(transport)
        self.subagents = SubagentsApi(transport)
        self.repositories = RepositoriesApi(transport)
        self.system = SystemApi(transport)
        self.clients = ClientsApi(transport)
        self.devices = DevicesApi(transport)
        self.logs = LogsApi(transport)
        self.language = LanguageApi(transport)
