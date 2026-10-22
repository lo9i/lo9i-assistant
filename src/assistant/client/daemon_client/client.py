import httpx

from assistant.client.daemon_client.alerts import AlertsApi
from assistant.client.daemon_client.channels import ChannelsApi
from assistant.client.daemon_client.clients import ClientsApi
from assistant.client.daemon_client.conversations import ConversationsApi
from assistant.client.daemon_client.devices import DevicesApi
from assistant.client.daemon_client.email import EmailApi
from assistant.client.daemon_client.events import EventsMixin
from assistant.client.daemon_client.files import FilesApi
from assistant.client.daemon_client.home import HomeApi
from assistant.client.daemon_client.identity import IdentityApi
from assistant.client.daemon_client.jobs import JobsApi
from assistant.client.daemon_client.logs import LogsApi
from assistant.client.daemon_client.mcp import McpApi
from assistant.client.daemon_client.memory import MemoryApi
from assistant.client.daemon_client.model import ModelApi
from assistant.client.daemon_client.notifications import NotificationsApi
from assistant.client.daemon_client.oauth import OAuthApi
from assistant.client.daemon_client.repositories import RepositoriesApi
from assistant.client.daemon_client.runs import RunsMixin
from assistant.client.daemon_client.sessions import SessionsMixin
from assistant.client.daemon_client.skills import SkillsApi
from assistant.client.daemon_client.speech import SpeechApi
from assistant.client.daemon_client.system import SystemApi
from assistant.client.daemon_client.tasks import TasksApi
from assistant.client.daemon_client.transport import Transport
from assistant.client.daemon_client.usage import UsageApi
from assistant.client.daemon_client.web_search import WebSearchApi


class DaemonClient(SessionsMixin, RunsMixin, EventsMixin):
    """Everything a client can ask the daemon. The conversation (sessions, runs, events) is on the
    client itself; everything else is grouped by the part of the daemon it changes."""

    def __init__(self, http: httpx.AsyncClient) -> None:
        transport = Transport(http)
        super().__init__(transport)
        self.conversations = ConversationsApi(transport)
        self.files = FilesApi(transport)
        self.identity = IdentityApi(transport)
        self.memory = MemoryApi(transport)
        self.skills = SkillsApi(transport)
        self.jobs = JobsApi(transport)
        self.usage = UsageApi(transport)
        self.channels = ChannelsApi(transport)
        self.speech = SpeechApi(transport)
        self.web_search = WebSearchApi(transport)
        self.model = ModelApi(transport)
        self.email = EmailApi(transport)
        self.oauth = OAuthApi(transport)
        self.mcp = McpApi(transport)
        self.alerts = AlertsApi(transport)
        self.notifications = NotificationsApi(transport)
        self.home = HomeApi(transport)
        self.tasks = TasksApi(transport)
        self.repositories = RepositoriesApi(transport)
        self.system = SystemApi(transport)
        self.clients = ClientsApi(transport)
        self.devices = DevicesApi(transport)
        self.logs = LogsApi(transport)
