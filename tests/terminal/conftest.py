"""A fake daemon client for driving the terminal app headlessly."""

import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

import assistant_terminal.tui.app as app_module
from assistant.core.agent import (
    Conversation,
    ConversationError,
    Device,
    DeviceError,
    EmailAccount,
    EmailError,
    FoundServer,
    InstalledFromRepository,
    InvalidNameError,
    InvalidTokenError,
    Job,
    JobError,
    McpServerError,
    McpServerStatus,
    McpToolInfo,
    MemorySnapshot,
    ModelSettingsError,
    ModelStatus,
    PairingCode,
    RepositoryContents,
    RepositoryError,
    RunRecord,
    ServerField,
    Session,
    ShownMessage,
    Skill,
    SkillError,
    SlackError,
    SlackStatus,
    SpeechSettingsError,
    SpeechStatus,
    TelegramStatus,
    TokenReport,
    UsageReport,
)
from assistant.core.agent.skills import FoundSkill, SkillSummary
from assistant.core.events import ApprovalRequired, Done, TextDelta, ToolFinished, ToolStarted, Transcribed
from assistant.core.integrations.email.providers import PROVIDERS
from assistant.core.llm.choice import PROVIDERS as PROVIDERS_FOR_MODEL
from assistant.core.repositories.known import EXTRAS
from assistant.core.usage.log import TokenRow, ToolUsage
from assistant.protocol import ConnectedClient, StartupError, StartupStatus
from assistant_terminal.history import History
from assistant_terminal.preferences import Preferences

_NEXT = "2030-01-01T09:00:00+00:00"


class FakeSkills:
    def __init__(self):
        self.items = {
            "news-digest": Skill("news-digest", "Daily news summary", "1. Search news\n2. Email it"),
            "weekly-review": Skill("weekly-review", "Friday review", "1. List the week"),
        }
        # Failures in a row, the last one, when, and whether it's failing, by skill.
        self.failures: dict[str, tuple[int, str, str, bool]] = {}

    async def list(self):
        return [
            SkillSummary(s.name, s.description, s.problems, *self.failures.get(s.name, (0, "", "", False)))
            for s in self.items.values()
        ]

    async def get(self, name):
        if name not in self.items:
            raise SkillError(f"No skill named {name}.")
        return self.items[name]

    async def update(self, name, description, instructions):
        if not description.strip() or not instructions.strip():
            raise SkillError("A skill needs a description and instructions.")
        self.items[name] = Skill(name, description, instructions)
        return self.items[name]

    async def delete(self, name):
        self.items.pop(name)

    async def update_installed(self, name):
        self.updated = name
        return self.items[name]


class FakeMemory:
    def __init__(self, skills: FakeSkills):
        self.profile = {}
        self._skills = skills

    async def snapshot(self):
        return MemorySnapshot(profile=self.profile, skills=sorted(self._skills.items))


class FakeUsage:
    async def report(self, days=7):
        tools = [
            ToolUsage("bash", 12, 1, 2, 850, "2026-09-30T09:00:00"),
            ToolUsage("web_search", 5, 0, 0, 1800, "2026-09-30T09:01:00"),
        ]
        return UsageReport(
            days, tools, [ToolUsage("news-digest", 3 if days == 7 else 12, 0, 0, 5, "2026-09-30T09:00:00")]
        )

    async def tokens(self, days=7):
        total = TokenRow(
            "total", calls=4, input_tokens=52_000, cache_read_tokens=40_000, output_tokens=1_800, cost=0.07
        )
        model = TokenRow(
            "claude-opus-5-5", calls=4, input_tokens=52_000, cache_read_tokens=40_000, output_tokens=1_800, cost=0.07
        )
        tool = TokenRow("web_fetch", calls=1, input_tokens=9_000, output_tokens=40)
        return TokenReport(days, total, by_model=[model], by_tool=[tool])


class FakeTelegram:
    def __init__(self):
        self.state = TelegramStatus(False, False, "", [], "", "")

    async def status(self):
        return self.state

    async def connect(self, token):
        if token != "111:GOOD":
            raise InvalidTokenError("Telegram rejected the token: Unauthorized")
        expires = (datetime.now(UTC) + timedelta(minutes=10)).isoformat()
        self.state = TelegramStatus(True, True, "lo9i_bot", [], "lo9i-4821", expires)
        return self.state

    async def start_pairing(self):
        return self.state

    async def disconnect(self):
        self.state = TelegramStatus(False, False, "", [], "", "")


class FakeSlack:
    def __init__(self):
        self.state = SlackStatus(False, False, "", "")

    async def status(self):
        return self.state

    async def manifest(self):
        return '{"display_information": {"name": "lo9i"}}'

    async def connect(self, app_token, bot_token, user_token):
        if app_token != "xapp-1":
            raise SlackError("Slack rejected the app token: invalid_auth")
        self.state = SlackStatus(True, False, "Acme", "ani")
        return self.state

    async def disconnect(self):
        self.state = SlackStatus(False, False, "", "")


class FakeEmail:
    def __init__(self):
        self.accounts_by_id: dict[str, EmailAccount] = {}
        self.connected_with = None

    async def providers(self):
        return list(PROVIDERS)

    async def accounts(self):
        return sorted(self.accounts_by_id.values(), key=lambda a: not a.default)

    async def add(self, label, host, port, username, password, sender, imap_host="", imap_port=993):
        self.connected_with = (label, host, port, username, password, sender, imap_host)
        if password != "right":
            raise EmailError("Couldn't log in: bad password")
        account_id = f"a{len(self.accounts_by_id) + 1}"
        default = not self.accounts_by_id
        self.accounts_by_id[account_id] = EmailAccount(
            account_id, label or sender, default, "ok", "", host, port, username, sender, [], imap_host, imap_port, ""
        )
        return self.accounts_by_id[account_id]

    async def update(self, account_id, label, host, port, username, password, sender, imap_host="", imap_port=993):
        self.connected_with = (label, host, port, username, password, sender, imap_host)
        account = self.accounts_by_id[account_id]
        account.label, account.host, account.sender, account.status = label or sender, host, sender, "ok"
        return account

    async def rename(self, account_id, label):
        account = self.accounts_by_id[account_id]
        account.label = label.strip() or account.sender
        return account

    async def make_default(self, account_id):
        for account in self.accounts_by_id.values():
            account.default = account.id == account_id
        return self.accounts_by_id[account_id]

    async def set_new_mail_alerts(self, account_id, channel):
        account = self.accounts_by_id[account_id]
        if channel and not account.imap_host:
            raise EmailError("Set up reading mail first.")
        account.new_mail_alerts = channel
        return account

    async def set_recipients(self, account_id, addresses):
        account = self.accounts_by_id[account_id]
        account.allowed_recipients = sorted(a.strip() for a in addresses if a.strip())
        return account

    async def remove(self, account_id):
        removed = self.accounts_by_id.pop(account_id)
        if removed.default and self.accounts_by_id:
            next(iter(self.accounts_by_id.values())).default = True


class FakeSpeech:
    def __init__(self):
        from assistant.core.agent.speech import LanguageOption, VoiceOption

        self.state = SpeechStatus(
            model="small",
            languages=["es", "en"],
            decoding="accurate",
            spoken_replies="off",
            voice="ef_dora",
            models=["tiny", "base", "small"],
            language_options=[LanguageOption("en", "English"), LanguageOption("es", "Spanish")],
            voice_options=[VoiceOption("ef_dora", "Dora", "Spanish"), VoiceOption("af_heart", "Heart", "English (US)")],
        )

    async def settings(self):
        return self.state

    async def change(self, model, languages, decoding=None):
        if not languages:
            raise SpeechSettingsError("Choose at least one language from the list.")
        self.state.model, self.state.languages = model, languages
        self.state.decoding = decoding or self.state.decoding
        return self.state

    async def change_replies(self, spoken_replies, voice):
        self.state.spoken_replies, self.state.voice = spoken_replies, voice or self.state.voice
        return self.state


def _env_model() -> ModelStatus:
    return ModelStatus("env", "anthropic", "claude-opus-5-5", "claude-sonnet-5-5", {}, ["api_key"])


class FakeModel:
    def __init__(self):
        self.state = _env_model()
        self.saved = None
        # Groq's package isn't installed yet, to show what saving will do.
        self.list = [replace(p, installed=p.id != "groq") for p in PROVIDERS_FOR_MODEL]

    async def providers(self):
        return self.list

    async def status(self):
        return self.state

    async def set(self, provider, values, model, worker_model):
        if values.get("api_key") == "bad":
            raise ModelSettingsError(f"{model} didn't answer: 401 invalid key")
        self.saved = (provider, values, model, worker_model)
        secret = {f.key for p in self.list if p.id == provider for f in p.fields if f.secret}
        plain = {k: v for k, v in values.items() if k not in secret}
        self.state = ModelStatus("app", provider, model, worker_model, plain, sorted(k for k in values if k in secret))
        return self.state

    async def reset(self):
        self.state = _env_model()
        return self.state


class FakeSystem:
    def __init__(self):
        self.state = StartupStatus(enabled=False, managed=False, includes_ollama=False)
        self.cancel_password = False
        # macos, linux or unsupported; on linux, whether lingering is on.
        self.platform = "macos"
        self.lingering = True

    async def startup_status(self):
        return self.state

    async def enable_startup(self):
        if self.cancel_password:
            raise StartupError("Cancelled.")
        ollama = self.platform == "macos"
        self.state = StartupStatus(True, False, ollama, self.platform, self.lingering)
        return self.state

    async def disable_startup(self):
        self.state = StartupStatus(False, False, False, self.platform, self.lingering)
        return self.state


def _mcp_status(name: str, trusted: bool = False, source: str = "") -> McpServerStatus:
    tools = [
        McpToolInfo("read_notes", "Read all notes.", True, True),
        McpToolInfo("add_note", "Add a note.", False, True),
    ]
    return McpServerStatus(
        name, "stdio", "notes-server", [], "", ["TOKEN"], [], True, trusted, [], [], "connected", "", tools, source
    )


class FakeMcp:
    def __init__(self):
        self.items = {"notes": _mcp_status("notes")}
        self.added = []

    async def servers(self):
        return list(self.items.values())

    async def probe(self, server):
        if not server.name:
            raise McpServerError("The name must be 1-24 lowercase letters.")
        return [McpToolInfo("search", "Search.", True, True), McpToolInfo("delete", "Delete.", False, True)]

    async def add(self, server):
        self.added.append(server)
        self.items[server.name] = _mcp_status(server.name, server.trusted)
        return self.items[server.name]

    async def change(self, name, changes):
        server = self.items[name]
        for field, value in vars(changes).items():
            if value is not None and hasattr(server, field):
                setattr(server, field, value)
        return server

    async def remove(self, name):
        del self.items[name]

    async def update_from_repository(self, name):
        self.updated = name
        return self.items[name]


class FakeRepositories:
    """Installs into the fake skills and MCP servers."""

    def __init__(self, skills: FakeSkills, mcp: FakeMcp):
        self._skills, self._mcp = skills, mcp
        self.installed: list = []
        self.unreachable = False

    async def browse(self, url=None):
        if self.unreachable:
            raise RepositoryError("Couldn't get the repository: no network")
        fields = [ServerField("CAL_USER", "User"), ServerField("CAL_PASSWORD", "Password", secret=True)]
        skill = "expenses" in self._skills.items
        return RepositoryContents(
            [FoundSkill("expenses", "Track expenses", ["scripts/add.py"], installed=skill)],
            [
                FoundServer("calendar", "Calendar", "stdio", fields, False, installed="calendar" in self._mcp.items),
                FoundServer(
                    "weather",
                    "Weather",
                    "stdio",
                    [],
                    False,
                    page=True,
                    installed="weather" in self._mcp.items,
                    version="1.1.0",
                    installed_version="1.0.0" if "weather" in self._mcp.items else "",
                ),
            ],
        )

    async def install(self, skills, servers, url=None):
        url = url or EXTRAS
        if any(s.name == "calendar" and (len(s.values) < 2 or not all(s.values.values())) for s in servers):
            raise RepositoryError("calendar needs Password.")
        self.installed.append((url, skills, servers))
        for name in skills:
            self._skills.items[name] = Skill(
                name, "Track expenses", "Run scripts/add.py", files=["scripts/add.py"], source=url
            )
        for server in servers:
            self._mcp.items[server.name] = _mcp_status(server.name, source=url)
        return InstalledFromRepository(
            [self._skills.items[n] for n in skills], [self._mcp.items[s.name] for s in servers]
        )


class FakeJobs:
    def __init__(self):
        self.items = {
            "daily-news": Job("daily-news", "owner", "0 9 * * *", "UTC", "Run the skill news-digest", _NEXT),
            "stretch": Job("stretch", "owner", "", "UTC", "Send the user: stretch", _NEXT, one_time=True),
        }
        self.items["daily-news"].runs = [RunRecord("2026-09-29T09:00:00+00:00", "ok", "Sent the digest.")]

    async def list(self):
        return sorted(self.items.values(), key=lambda j: j.name)

    async def set_enabled(self, name, enabled):
        self.items[name].enabled = enabled
        return self.items[name]

    async def delete(self, name):
        if name not in self.items:
            raise JobError(f"No job named {name}.")
        self.items.pop(name)


class FakeIdentity:
    def __init__(self):
        self.current = ""

    async def name(self):
        return self.current

    async def rename(self, name):
        if not name.strip():
            raise InvalidNameError("The name can't be empty.")
        self.current = name.strip()
        return self.current


class FakeConversations:
    def __init__(self):
        self.items = [Conversation("owner:abc", "plan my trip", _NEXT, _NEXT)]
        self.said = {"owner:abc": [ShownMessage("user", "plan my trip"), ShownMessage("assistant", "Rome it is.")]}

    async def recent(self):
        return list(self.items)

    async def messages(self, thread_id):
        return self.said.get(thread_id, [])

    async def delete(self, thread_id):
        self.items = [c for c in self.items if c.thread_id != thread_id]


class FakeDevices:
    def __init__(self):
        self.items = [Device("d1", "Laptop", "2026-09-01T09:00:00+00:00", "2026-09-30T09:00:00+00:00", "203.0.113.7")]
        self.codes = 0

    async def list(self):
        return list(self.items)

    async def open_pairing(self):
        self.codes += 1
        return PairingCode("K7QM-2XPD", "2030-01-01T09:10:00+00:00")

    async def revoke(self, device_id):
        if device_id not in {d.id for d in self.items}:
            raise DeviceError(f"No device {device_id}.")
        self.items = [d for d in self.items if d.id != device_id]


class FakeClients:
    own_id = "me"

    def __init__(self):
        self.connected = [ConnectedClient("me", "cli", "unix socket", "2026-09-30T09:00:00.123+00:00")]

    async def list(self):
        return list(self.connected)


class FakeClient:
    """DaemonClient's shape: the conversation on the client, everything else in groups."""

    def __init__(self):
        self.sent, self.decisions, self.cancelled = [], None, []
        self.bus = asyncio.Queue()
        self.runs = {}
        self.active_thread = "owner:abc"
        self.identity = FakeIdentity()
        self.skills = FakeSkills()
        self.jobs = FakeJobs()
        self.memory = FakeMemory(self.skills)
        self.usage = FakeUsage()
        self.telegram = FakeTelegram()
        self.slack = FakeSlack()
        self.email = FakeEmail()
        self.system = FakeSystem()
        self.clients = FakeClients()
        self.conversations = FakeConversations()
        self.devices = FakeDevices()
        self.mcp = FakeMcp()
        self.repositories = FakeRepositories(self.skills, self.mcp)
        self.model = FakeModel()
        self.speech = FakeSpeech()

    async def send(self, session, text, attachments=()):
        self.sent.append((text, [(a.name, a.media_type) for a in attachments]))
        if any(a.media_type.startswith("audio/") for a in attachments):
            yield Transcribed("hola", "es")
        yield ToolStarted("bash", {"command": "ls -la"})
        yield ToolFinished("bash", "exit code: 0\nfile1")
        yield ToolStarted("bash", {"command": "rm -rf build"})
        yield ApprovalRequired("i1", {"tool": "bash", "command": "rm -rf build", "reason": "recursive delete"})

    async def resume(self, session, decisions):
        self.decisions = decisions
        yield ToolFinished("bash", "exit code: 0")
        for word in ["## Done\n\n", "Listed **1 file**."]:
            await asyncio.sleep(0)
            yield TextDelta(word)
        self.memory.profile = {"work": ["backend engineer"]}
        yield Done()

    async def new_thread(self, user_id):
        return "owner:new"

    async def cancel(self, session):
        self.cancelled.append(session.thread_id)
        return True

    async def resume_thread(self, user_id, thread_id):
        if thread_id not in {c.thread_id for c in self.conversations.items}:
            raise ConversationError(f"No conversation {thread_id}.")
        self.active_thread = thread_id

    async def events(self):
        while True:
            yield await self.bus.get()

    def follow_run(self, run_id):
        return self.runs[run_id]()


@pytest.fixture
def client():
    return FakeClient()


@pytest.fixture
def app(client, monkeypatch, tmp_path):
    monkeypatch.setattr(app_module, "recording_available", lambda: False)
    history = History(tmp_path / "cli_history", limit=100)
    preferences = Preferences(tmp_path / "cli_preferences.json")
    return app_module.AssistantApp(client, Session("owner", "cli", "owner:abc"), history, preferences)


async def wait_for(pilot, condition, seconds=5.0):
    for _ in range(int(seconds / 0.05)):
        if condition():
            return
        await pilot.pause(0.05)
    raise AssertionError("condition not met in time")
