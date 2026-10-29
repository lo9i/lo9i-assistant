"""A fake daemon client for driving the terminal app headlessly."""

import asyncio
from dataclasses import replace
from pathlib import Path

import httpx
import pytest

import assistant_terminal.tui.app as app_module
from assistant.client.daemon_client.conversations import OpenedConversation
from assistant.core.agent import (
    Agent,
    AgentFolders,
    ChannelNotConnectedError,
    ChannelStatus,
    Conversation,
    ConversationError,
    ConversationStats,
    Device,
    DeviceError,
    EmailAccount,
    EmailError,
    Episode,
    Fact,
    FolderListing,
    FoundServer,
    Handoff,
    HandoffError,
    HomeCard,
    HomeItem,
    HomePage,
    HomeSection,
    HomeSectionsError,
    InstalledFromRepository,
    InvalidNameError,
    InvalidSearchKeyError,
    Job,
    JobError,
    KeptKeys,
    LanguageError,
    McpProbe,
    McpServerError,
    McpServerStatus,
    McpToolInfo,
    MemoryEditError,
    MemorySnapshot,
    ModelSettingsError,
    ModelStatus,
    Notification,
    PairingCode,
    PluginUpdate,
    PromptEditError,
    PromptSection,
    Repository,
    RepositoryContents,
    RepositoryError,
    RepositoryPlugins,
    RunRecord,
    SectionResult,
    ServerField,
    Session,
    SetupItem,
    ShownCall,
    ShownMessage,
    SignedIn,
    SignInError,
    Skill,
    SkillError,
    SpeechSettingsError,
    SpeechStatus,
    TokenReport,
    UploadedFile,
    UsageReport,
    WebSearchStatus,
)
from assistant.core.agent.skill_imports import Importable, Importables, ImportOutcome
from assistant.core.agent.skills import FoundSkill, SkillSummary
from assistant.core.conversation.dispatch_setting import DispatchSetting, DispatchSettingError
from assistant.core.doctor.model import Cause, ContextPart, DoctorPage, DoctorReport, KnownCause, StartingContext
from assistant.core.events import ApprovalRequired, Dispatched, Done, TextDelta, ToolFinished, ToolStarted, Transcribed
from assistant.core.integrations.email.providers import EmailProvider
from assistant.core.llm.choice import PROVIDERS as PROVIDERS_FOR_MODEL
from assistant.core.logs import COMPONENTS, LogEntry, LogFileInfo, LogOptions, LogPage, LogQuery
from assistant.core.repositories.known import EXTRAS
from assistant.core.usage.log import TokenRow, ToolUsage
from assistant.protocol import (
    Commit,
    ConnectedClient,
    HostStatus,
    NoEndingError,
    PendingEnding,
    ShutdownStatus,
    StartupError,
    StartupStatus,
    StopRefusedError,
    UpdateError,
    UpdateStatus,
)
from assistant_terminal import i18n
from assistant_terminal.history import History
from assistant_terminal.preferences import Preferences

_NEXT = "2030-01-01T09:00:00+00:00"
# Put on FakeClient.bus: the event stream drops, then opens again.
LOST, OPEN = "<stream lost>", "<stream open>"


class FakeSkills:
    def __init__(self):
        self.items = {
            "news-digest": Skill("news-digest", "Daily news summary", "1. Search news\n2. Email it"),
            "weekly-review": Skill("weekly-review", "Friday review", "1. List the week"),
        }
        # Failures in a row, the last one, when, and whether it's failing, by skill.
        self.failures: dict[str, tuple[int, str, str, bool]] = {}
        # Claude Code's and Codex's skills, and the imports asked for: (ids, replace).
        self.importables = [
            Importable(
                "/h/.claude/skills/pdf",
                "claude",
                "Claude Code",
                "skills",
                "",
                "pdf",
                "Fill PDF forms",
                [],
                "new",
                "pdf",
            ),
            Importable(
                "/h/.agents/skills/edit",
                "codex",
                "Codex",
                "skills",
                "",
                "edit",
                "Edit files",
                [],
                "new",
                "edit",
                needs_agent=["It uses a coding agent's tools: Edit."],
            ),
        ]
        self.imports: list[tuple[list[str], bool]] = []

    async def importable(self):
        return Importables(self.importables, ["/h/.claude/CLAUDE.md"])

    async def import_skills(self, ids, replace=False):
        self.imports.append((list(ids), replace))
        return [ImportOutcome(i, "imported", i.rsplit("/", 1)[-1]) for i in ids]

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
        self.saved_facts = [Fact("f1", "likes jazz", "2026-10-01T09:00:00")]
        self.saved_episodes = [Episode("2026-10-01T09:00", "2026-10-01T10:00", "Planned a trip", "e1")]

    async def facts(self):
        return list(self.saved_facts)

    async def edit_fact(self, fact_id, text):
        if not text.strip():
            raise MemoryEditError("Write something, or delete it instead.")
        self.saved_facts = [Fact(f"{fact_id}+", text) if f.id == fact_id else f for f in self.saved_facts]
        return self.saved_facts[0]

    async def delete_fact(self, fact_id):
        self.saved_facts = [f for f in self.saved_facts if f.id != fact_id]

    async def episodes(self):
        return list(self.saved_episodes)

    async def edit_episode(self, episode_id, summary):
        self.saved_episodes = [
            Episode(e.started_at, e.ended_at, summary, f"{episode_id}+") if e.id == episode_id else e
            for e in self.saved_episodes
        ]
        return self.saved_episodes[0]

    async def delete_episode(self, episode_id):
        self.saved_episodes = [e for e in self.saved_episodes if e.id != episode_id]

    async def snapshot(self):
        sections = ["about", "people", "how_to_reply", "routine", "goals", "interests", "dislikes", "work"]
        profile = {name: items for name, items in self.profile.items() if items}
        return MemorySnapshot(profile=profile, profile_sections=sections, skills=sorted(self._skills.items))

    async def set_profile_section(self, section, items):
        self.profile[section] = [item.strip() for item in items if item.strip()]
        return await self.snapshot()


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


class FakeChannels:
    """One channel, telegram, installed but not connected until a test says so."""

    def __init__(self):
        self.items = {"telegram": ChannelStatus("telegram", True, False, [SetupItem("text", "", "Starting…")])}
        self.pressed = []

    async def list(self):
        return list(self.items.values())

    async def press(self, name, action):
        if not self.items[name].connected:
            raise ChannelNotConnectedError(f"{name} isn't connected.")
        self.pressed.append((name, action))


class FakeWebSearch:
    def __init__(self):
        self.state = WebSearchStatus(brave_key_set=False)

    async def status(self):
        return self.state

    async def set_brave_key(self, key):
        if key != "GOOD":
            raise InvalidSearchKeyError("Brave didn't accept the key: 401 Unauthorized")
        self.state = WebSearchStatus(brave_key_set=True)
        return self.state

    async def remove_brave_key(self):
        self.state = WebSearchStatus(brave_key_set=False)
        return self.state


# The installed email plugins: gmail with an app password, microsoft signing in, custom-email with
# servers the user types.
_PROVIDERS = [
    EmailProvider(
        "gmail",
        "Gmail",
        "smtp.gmail.com",
        587,
        "imap.gmail.com",
        "Gmail needs an app password.",
        "https://myaccount.google.com/apppasswords",
        plugin="gmail",
    ),
    EmailProvider(
        "microsoft",
        "Outlook.com",
        "smtp.office365.com",
        587,
        "outlook.office365.com",
        "Microsoft needs an app registration.",
        oauth="microsoft",
        plugin="microsoft",
    ),
    EmailProvider("custom", "Other server", "", 587, "", "Use an app password.", plugin="custom-email", custom=True),
]


class FakeEmail:
    def __init__(self):
        self.accounts_by_id: dict[str, EmailAccount] = {}
        self.allowed: list[str] = []
        self.connected_with = None

    async def providers(self):
        return list(_PROVIDERS)

    async def accounts(self):
        return sorted(self.accounts_by_id.values(), key=lambda a: not a.default)

    async def add(self, label, host, port, username, password, sender, imap_host="", imap_port=993, plugin=""):
        self.connected_with = (label, host, port, username, password, sender, imap_host)
        if password != "right":
            raise EmailError("Couldn't log in: bad password")
        account_id = f"a{len(self.accounts_by_id) + 1}"
        default = not self.accounts_by_id
        self.accounts_by_id[account_id] = EmailAccount(
            account_id,
            label or sender,
            default,
            "ok",
            "",
            host,
            port,
            username,
            sender,
            imap_host,
            imap_port,
            "",
            plugin=plugin,
        )
        return self.accounts_by_id[account_id]

    async def update(self, account_id, label, host, port, username, password, sender, imap_host="", imap_port=993):
        self.connected_with = (label, host, port, username, password, sender, imap_host)
        account = self.accounts_by_id[account_id]
        account.label, account.host, account.sender, account.status = label or sender, host, sender, "ok"
        return account

    async def start_sign_in(
        self, provider, client_id, client_secret, redirect_uri, address, label="", account_id="", plugin=""
    ):
        if not client_id and not account_id:
            raise EmailError("Enter the email address and your OAuth app's client ID.")
        self.sign_in = (provider, client_id, client_secret, redirect_uri, address, label, account_id, plugin)
        return f"https://login.example.com/authorize?state=s1&redirect_uri={redirect_uri}"

    def finish_sign_in(self) -> EmailAccount:
        provider, _, _, _, address, label, _, plugin = self.sign_in
        account_id = f"a{len(self.accounts_by_id) + 1}"
        self.accounts_by_id[account_id] = EmailAccount(
            account_id,
            label or address,
            not self.accounts_by_id,
            "ok",
            "",
            "smtp.office365.com",
            587,
            address,
            address,
            "outlook.office365.com",
            993,
            "",
            "oauth",
            provider,
            plugin,
        )
        return self.accounts_by_id[account_id]

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

    async def recipients(self):
        return self.allowed

    async def set_recipients(self, addresses):
        self.allowed = sorted(a.strip() for a in addresses if a.strip())
        return self.allowed

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
        self.dispatching = DispatchSetting()
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

    async def dispatch(self):
        return self.dispatching

    async def set_dispatch(self, setting):
        if not 0 <= setting.confidence <= 1:
            raise DispatchSettingError("The confidence goes from 0 to 1.")
        self.dispatching = setting
        return setting


class FakeSystem:
    def __init__(self, bus: asyncio.Queue):
        # As the daemon does, a restart or stop asked for is announced to every app (an `ending` event).
        self._bus = bus
        self.update_now = UpdateStatus(
            installed_from="git",
            current=Commit("a1b2c3d4", "First", "2026-10-24T12:00:00Z"),
            upstream="origin/main",
            behind=0,
            new=[],
            checked_at="",
            can_update=False,
            reason="",
            state="idle",
            step="",
            error="",
        )
        # What a check finds next.
        self.upstream_has: list[Commit] = []
        self.updates_started = 0
        self.state = StartupStatus(enabled=False, managed=False, includes_ollama=False)
        self.cancel_password = False
        self.reinstalled = 0
        # macos, linux or unsupported; on linux, whether lingering is on.
        self.platform = "macos"
        self.lingering = True
        self.host_reads = 0
        # "restart" and "stop", as asked; a stop is refused with this reason when it's set.
        self.endings: list[str] = []
        self.stop_refusal = ""
        # The runs a restart or stop asked for waits for; "now" cancels them.
        self.runs = 0
        self.pending = PendingEnding("", 0)
        self.cancelled_runs = 0

    async def startup_status(self):
        return self.state

    async def host(self):
        self.host_reads += 1
        return HostStatus(
            "Linux 7.0.0",
            "x86_64",
            "board",
            "CPython 3.12.9",
            "0.1.0",
            4,
            5.0,
            2 * 1024**3,
            4 * 1024**3,
            20 * 1024**3,
            100 * 1024**3,
            90_060,
            [0.09, 0.09, 0.04],
            self.stop_refusal,
        )

    async def enable_startup(self):
        if self.cancel_password:
            raise StartupError("Cancelled.")
        ollama = self.platform == "macos"
        self.state = StartupStatus(True, False, ollama, self.platform, self.lingering)
        return self.state

    async def disable_startup(self):
        self.state = StartupStatus(False, False, False, self.platform, self.lingering)
        return self.state

    async def reinstall_startup(self):
        self.reinstalled += 1
        self.state = replace(self.state, outdated=[])
        return self.state

    async def restart(self):
        return await self._end("restart", self.runs)

    async def stop(self):
        if self.stop_refusal:
            raise StopRefusedError(self.stop_refusal)
        return await self._end("stop", max(self.runs, 1))

    async def _end(self, ending, runs):
        self.endings.append(ending)
        if runs:
            self.pending = PendingEnding(ending, runs, can_take_back=True)
        await self._bus.put(("ending", ending_event(ending, runs, taken_back=False)))
        return ShutdownStatus(waiting_for_runs=runs)

    async def ending(self):
        return self.pending

    async def take_back_ending(self):
        if not self.pending.ending:
            raise NoEndingError("No restart or stop is waiting to be taken back.")
        ending, self.pending = self.pending.ending, PendingEnding("", 0)
        await self._bus.put(("ending", ending_event(ending, 0, taken_back=True)))
        return self.pending

    async def end_now(self):
        if not self.pending.ending:
            raise NoEndingError("No restart or stop is waiting for runs.")
        self.cancelled_runs, self.pending = self.pending.waiting_for_runs, PendingEnding("", 0)
        return self.cancelled_runs

    async def update_status(self):
        return self.update_now

    async def check_for_update(self):
        new = self.upstream_has
        self.update_now = replace(self.update_now, checked_at="now", new=new, behind=len(new), can_update=True)
        return self.update_now

    async def update(self):
        if not self.update_now.behind:
            raise UpdateError("lo9i is up to date.")
        self.updates_started += 1
        self.update_now = replace(self.update_now, state="updating", step="Downloading the update")
        return self.update_now


def _mcp_status(name: str, trusted: bool = False, source: str = "") -> McpServerStatus:
    tools = [
        McpToolInfo("read_notes", "Read all notes.", True, True),
        McpToolInfo("add_note", "Add a note.", False, True),
    ]
    return McpServerStatus(
        name, "stdio", "notes-server", [], "", ["TOKEN"], [], True, trusted, [], [], "connected", "", tools, source
    )


def _built_in_home() -> list[HomeSection]:
    return [HomeSection(id="calendar", title="Calendar", prompt="Today's events.", plugins=["calendar"])]


class FakeHome:
    """Home with the built-in Calendar section, built once, and the sections as saved."""

    def __init__(self):
        self.sections = _built_in_home()
        self.results = {
            "calendar": SectionResult(
                section_id="calendar",
                title="Calendar",
                status="ok",
                items=[HomeItem(title="Dentist", subtitle="Av. Corrientes 1234", time="09:30")],
                at="2026-10-24T08:00:00+00:00",
            )
        }
        self.refreshes: list[bool] = []
        self.watching = False
        self.refusal = ""

    def _page(self) -> HomePage:
        cards = [HomeCard(section=s, result=self.results.get(s.id)) for s in self.sections]
        return HomePage(cards=cards, updated_at="2026-10-24T08:00:00+00:00")

    async def get(self):
        return self._page()

    async def refresh(self, force=False):
        self.refreshes.append(force)
        return self._page()

    async def watch(self):
        self.watching = True

    async def unwatch(self):
        self.watching = False

    async def save_sections(self, sections):
        if self.refusal:
            raise HomeSectionsError(self.refusal)
        self.sections = [s if s.id else s.model_copy(update={"id": f"s{i}"}) for i, s in enumerate(sections)]
        return self._page()

    async def reset_sections(self):
        self.sections = _built_in_home()
        return self._page()


class FakeMcp:
    def __init__(self):
        self.items = {"notes": _mcp_status("notes")}
        self.added = []

    async def servers(self):
        return list(self.items.values())

    async def probe(self, server):
        if not server.name:
            raise McpServerError("The name must be 1-24 lowercase letters.")
        if server.url:
            return McpProbe([], sign_in=True)
        return McpProbe([McpToolInfo("search", "Search.", True, True), McpToolInfo("delete", "Delete.", False, True)])

    async def start_sign_in(self, name, redirect_uri):
        self.signing_in = (name, redirect_uri)
        return f"https://auth.example.com/authorize?state=m1&redirect_uri={redirect_uri}"

    def finish_sign_in(self) -> None:
        name, _ = self.signing_in
        self.items[name].status, self.items[name].error = "connected", ""

    async def start_plugin_sign_in(self, name, redirect_uri, client_id="", client_secret=""):
        if not client_id and not self.items[name].signed_in_as:
            raise McpServerError("Enter your OAuth app's client ID.")
        self.plugin_signing_in = (name, redirect_uri, client_id, client_secret)
        return f"https://accounts.google.com/o/oauth2/v2/auth?state=p1&redirect_uri={redirect_uri}"

    def finish_plugin_sign_in(self) -> None:
        self.items[self.plugin_signing_in[0]].signed_in_as = "me@gmail.com"

    async def sign_out_plugin(self, name):
        self.items[name].signed_in_as = ""
        return self.items[name]

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

    async def remove(self, name, delete_data=False):
        del self.items[name]
        self.data_deleted = delete_data
        # What a removed plugin leaves kept, as the daemon reports it.
        return KeptKeys(name, ["API_KEY"]) if getattr(self, "keeps_keys", False) else None

    async def update_from_repository(self, name):
        self.updated = name
        return self.items[name]


class FakeRepositories:
    """Installs into the fake skills and MCP servers."""

    def __init__(self, skills: FakeSkills, mcp: FakeMcp):
        self._skills, self._mcp = skills, mcp
        self.installed: list = []
        self.unreachable = False
        self.checks = True
        # Installed plugins the extras have a newer version of, as the daemon reports them.
        self.pending: list[PluginUpdate] = []
        # More servers the extras offer, for a test to add (a chat channel).
        self.more: list[FoundServer] = []
        # Repositories the user added, each offering `mine`.
        self.added: list[str] = []
        self.mine: list[FoundServer] = []

        # Tokens the private ones were added with, by address.
        self.tokens: dict[str, str] = {}
        # When the listings kept were last checked, and checks made (each reaches the repositories).
        self.last_check = "2029-12-31T09:00:00+00:00"
        self.checks_made = 0
        self.check_fails = False
        # What removed plugins left kept.
        self.kept: list[KeptKeys] = []

    async def forget_keys(self, kept):
        self.forgotten = kept
        self.kept = [k for k in self.kept if k != kept]

    async def kept_keys(self):
        return list(self.kept)

    async def list(self):
        return [Repository(EXTRAS, "lo9i/lo9i-assistant-extras", True)] + [
            Repository(url, url.removeprefix("https://github.com/"), False, url in self.tokens) for url in self.added
        ]

    async def add(self, url, token=""):
        if not url.startswith("https://"):
            raise RepositoryError("Give the repository's https:// address.")
        self.added.append(url)
        if token:
            self.tokens[url] = token
        return (await self.list())[-1]

    async def remove(self, url):
        self.added.remove(url)
        self.tokens.pop(url, None)

    async def plugins(self, cached=False):
        """`cached`: as last checked (`last_check`); otherwise a check, which fails when `check_fails`."""
        if not cached:
            self.checks_made += 1
            if self.check_fails:
                raise httpx.ConnectError("no network")
            self.last_check = "2030-01-01T09:00:00+00:00"
        if self.unreachable:
            extras = RepositoryPlugins((await self.list())[0], None, "Couldn't get the repository: no network")
            return [extras]
        listed = await self.list()
        mine = [RepositoryPlugins(r, RepositoryContents([], list(self.mine), [], self.last_check)) for r in listed[1:]]
        return [RepositoryPlugins(listed[0], replace(await self.browse(), checked=self.last_check)), *mine]

    async def updates(self):
        return list(self.pending) if self.checks else []

    async def update_checks(self):
        return self.checks

    async def set_update_checks(self, enabled):
        self.checks = enabled
        return enabled

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
                *self.more,
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

    async def run_reply(self, name, at):
        if not any(r.at == at for r in self.items[name].runs):
            raise JobError(f"{name} has no run at {at}.")
        return "Sent the digest: three headlines, the weather and the markets, in full."


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


class FakeLanguage:
    def __init__(self):
        self.current = "auto"

    async def get(self):
        return self.current

    async def set(self, language):
        if language not in ("auto", "en", "es"):
            raise LanguageError(f"Unknown language: {language}. Choose one of: auto, en, es.")
        self.current = language
        return language


class FakeTasks:
    def __init__(self):
        self.tasks = []

    async def running(self):
        return list(self.tasks)


class FakeConversations:
    def __init__(self):
        self.items = [Conversation("owner:abc", "plan my trip", _NEXT, _NEXT)]
        self.said = {"owner:abc": [ShownMessage("user", "plan my trip"), ShownMessage("assistant", "Rome it is.")]}
        self.pins: dict[str, list[str]] = {}
        self.handoffs: dict[str, Handoff] = {}
        # What each conversation's run stopped for and still waits on, whoever started it.
        self.waiting: dict[str, list[ApprovalRequired]] = {}
        # Tool calls in full, by conversation and call id.
        self.calls: dict[tuple[str, str], ShownCall] = {}
        # The runs in progress in each conversation, as `live` lists them.
        self.in_progress: dict[str, list[dict]] = {}
        # How full each conversation's context is: tokens, limit, and the agent's name while handed to one.
        self.context: dict[str, tuple[int, int, str]] = {}

    async def pending_approvals(self, thread_id):
        return self.waiting.pop(thread_id, [])

    async def tool_call(self, thread_id, call_id):
        if (thread_id, call_id) not in self.calls:
            raise ConversationError("No such tool call in this conversation.")
        return self.calls[(thread_id, call_id)]

    async def tool_call_step(self, thread_id, call_id, index):
        return await self.tool_call(thread_id, f"{call_id}#{index}")

    async def recent(self):
        return list(self.items)

    async def get(self, thread_id):
        return next((c for c in self.items if c.thread_id == thread_id), None)

    async def messages(self, thread_id):
        return self.said.get(thread_id, [])

    async def stats(self, thread_id):
        tokens, limit, agent = self.context.get(thread_id, (0, 0, ""))
        return ConversationStats(thread_id, 0, 0, 0, 0, 0, 0, None, None, tokens, limit, agent)

    async def live(self, thread_id):
        return OpenedConversation(self.said.get(thread_id, []), self.in_progress.get(thread_id, []))

    async def delete(self, thread_id):
        self.items = [c for c in self.items if c.thread_id != thread_id]

    async def agents(self):
        return [Agent("claude-code", "claude", "Claude Code")]

    async def agent(self, thread_id):
        return self.handoffs.get(thread_id)

    async def agent_folders(self):
        return AgentFolders("/home/me/.lo9i/claude-workspace", ["/home/me/projects/app"], "/home/me")

    async def child_folders(self, path, hidden=False):
        inside = {
            "/home/me": ["/home/me/projects"],
            "/home/me/projects": ["/home/me/projects/app", "/home/me/projects/new"],
        }
        found = inside.get(path, [])
        if hidden and path == "/home/me":
            found = ["/home/me/.config", *found]
        return FolderListing(path, str(Path(path).parent), found)

    async def hand_to(self, thread_id, command, folder):
        if not folder.startswith("/"):
            raise HandoffError(f"{folder} isn't an existing folder. Give its full path.")
        self.handoffs[thread_id] = Handoff("claude-code", command, "Claude Code", folder)
        return self.handoffs[thread_id]

    async def take_back(self, thread_id):
        self.handoffs.pop(thread_id, None)

    async def pinned(self, thread_id):
        return list(self.pins.get(thread_id, []))

    async def pin(self, thread_id, name):
        if name != "coding":
            raise SkillError(f"No skill named {name}.")
        self.pins.setdefault(thread_id, []).append(name)
        return await self.pinned(thread_id)

    async def unpin(self, thread_id, name):
        self.pins[thread_id] = [s for s in self.pins.get(thread_id, []) if s != name]
        return await self.pinned(thread_id)


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


def ending_event(ending: str, runs: int, taken_back: bool, update: bool = False, can_take_back: bool = True) -> dict:
    """As the daemon announces a restart or stop (daemon/server.py::_announcer)."""
    return {
        "ending": ending,
        "waiting_for_runs": runs,
        "waiting_for_update": update,
        "can_take_back": can_take_back,
        "taken_back": taken_back,
    }


class FakeFiles:
    def __init__(self):
        self.pages = []
        self.items = [
            UploadedFile(
                "a1/notes.txt",
                "notes.txt",
                "text/plain",
                2048,
                "2026-09-30T09:00:00+00:00",
                "owner:abc",
                "Groceries",
                "",
            ),
            UploadedFile(
                "b2/chart.png",
                "chart.png",
                "image/png",
                512,
                "2026-09-29T09:00:00+00:00",
                "owner:abc",
                "Groceries",
                "mcp__sheets__chart",
            ),
        ]

    async def list(self, query="", offset=0, limit=None):
        self.pages.append((offset, limit))
        return self.items[offset : None if limit is None else offset + limit]

    async def content(self, file):
        return b"buy milk"


class FakeClients:
    own_id = "me"

    def __init__(self):
        self.connected = [ConnectedClient("me", "cli", "unix socket", "2026-09-30T09:00:00.123+00:00")]

    async def list(self):
        return list(self.connected)


def _log(level: str, message: str, component: str = "mcp") -> LogEntry:
    return LogEntry("2026-10-07 10:00:00,000", level, f"assistant.core.{component}.x", component, message)


class FakeLogs:
    """The daemon log: a page from `entries`, filtered like the daemon does, and a live follow that
    sends a page, then whatever is put in `live`."""

    def __init__(self):
        self.entries = [_log("INFO", "connected"), _log("WARNING", "slow"), _log("ERROR", "crashed", "agent")]
        self.live: asyncio.Queue[LogEntry] = asyncio.Queue()
        self.following = 0
        self.recorded = "INFO"

    async def options(self):
        files = [LogFileInfo(n, f"{n}.log", "", f"/logs/{n}.log", 10) for n in ("daemon", "errors")]
        return LogOptions(files, ["DEBUG", "INFO", "WARNING", "ERROR"], list(COMPONENTS))

    async def page(self, name, level="", component="", lines=100):
        query = LogQuery(level, component, lines)
        entries = [e for e in self.entries if query.matches(e)][-lines:]
        return LogPage(LogFileInfo(name, f"{name}.log", "", f"/logs/{name}.log", 10), entries)

    async def level(self):
        return self.recorded

    async def set_level(self, level):
        self.recorded = level
        return level

    async def follow(self, name, level="", component="", lines=100):
        self.following += 1
        try:
            yield await self.page(name, level, component, lines)
            while True:
                yield await self.live.get()
        finally:
            self.following -= 1


class FakeOAuth:
    """The browser coming back with the code, for the email account or MCP server that asked last."""

    def __init__(self, email: FakeEmail, mcp: FakeMcp):
        self._email = email
        self._mcp = mcp

    async def finish(self, state, code):
        if state == "s1":
            account = self._email.finish_sign_in()
            return SignedIn("email", account.id, account.sender)
        if state == "m1":
            self._mcp.finish_sign_in()
            name = self._mcp.signing_in[0]
            return SignedIn("mcp", name, name)
        if state == "p1":
            self._mcp.finish_plugin_sign_in()
            name = self._mcp.plugin_signing_in[0]
            return SignedIn("plugin", name, name)
        raise SignInError("This sign-in has expired or was already used.")


class FakeDoctor:
    """The latest check found a growing failure and a warning, and nothing is known noise yet."""

    def __init__(self):
        self.report = DoctorReport(
            day="2026-10-24",
            at="2026-10-24T23:59:00+00:00",
            whole_day=True,
            compared_with="2026-10-23",
            causes=[
                _cause("c1", "ConnectionError: refused", 3, change="growing", before=1),
                _cause("c2", "Poll failed", 1, level="WARNING", where="assistant.core.channels.telegram"),
            ],
            gone=[_cause("c3", "KeyError: 'title'", 1)],
            context=StartingContext(
                tokens=12_000,
                window=150_000,
                parts=[
                    ContextPart(name="Saved facts", tokens=3100, before=2300),
                    ContextPart(name="Skills", tokens=900),
                ],
            ),
        )
        self.known: list[KnownCause] = []
        self.checks = 0

    def _page(self) -> DoctorPage:
        return DoctorPage(report=self.report, known=list(self.known))

    async def get(self):
        return self._page()

    async def check(self):
        self.checks += 1
        return self._page().model_copy(update={"checking": True})

    async def mark_known(self, cause_id):
        cause = next(c for c in self.report.causes if c.id == cause_id)
        self.known.append(KnownCause(id=cause.id, kind=cause.kind, title=cause.title, at="2026-10-25T08:00:00+00:00"))
        self.report = self.report.model_copy(update={"causes": [c for c in self.report.causes if c.id != cause_id]})
        return self._page()

    async def forget_known(self, cause_id):
        self.known = [k for k in self.known if k.id != cause_id]
        return self._page()


def _cause(id: str, title: str, count: int, **fields) -> Cause:
    times = {"first": "2026-10-24T09:00:00+00:00", "last": "2026-10-24T11:00:00+00:00"}
    defaults = {"kind": "log", "level": "ERROR", "where": "assistant/core/mcp/hub.py in _connect"}
    return Cause.model_validate({"id": id, "title": title, "count": count, **times, **defaults, **fields})


class FakeNotifications:
    def __init__(self):
        self.pages = []
        self.items = [
            Notification("n1", _NEXT, "background", "plan my trip", "✅ Claude Code finished.", True, "owner:abc"),
            Notification(
                "n2",
                _NEXT,
                "job",
                "Job daily-news",
                "Sent the digest.",
                True,
                job="daily-news",
                run_at="2026-09-29T09:00:00+00:00",
            ),
        ]

    async def list(self, offset=0, limit=None):
        self.pages.append((offset, limit))
        return self.items[offset : None if limit is None else offset + limit]

    async def mark_read(self):
        self.items = [replace(n, read=True) for n in self.items]

    async def dismiss(self, notification_id):
        self.items = [n for n in self.items if n.id != notification_id]

    async def clear(self):
        self.items = []


class FakePrompts:
    def __init__(self):
        self.items = {
            name: PromptSection(name, title, f"About the {title.lower()}.", text, text, False)
            for name, title, text in (
                ("persona", "Persona", "You are the assistant."),
                ("operating", "Operating instructions", "Work carefully."),
                ("channels", "Channels", "Write short lines."),
            )
        }

    async def list(self):
        return list(self.items.values())

    async def save(self, name, text):
        if not text.strip():
            raise PromptEditError("Write the text, or reset it to the built-in one.")
        section = self.items[name]
        self.items[name] = replace(section, text=text, edited=text != section.default, built_in_changes="")
        return self.items[name]

    async def keep(self, name):
        self.items[name] = replace(self.items[name], built_in_changes="")
        return self.items[name]

    async def reset(self, name):
        section = self.items[name]
        self.items[name] = replace(section, text=section.default, edited=False, built_in_changes="")
        return self.items[name]


class FakeClient:
    """DaemonClient's shape: the conversation on the client, everything else in groups."""

    def __init__(self):
        self.sent, self.decisions, self.cancelled = [], None, []
        # What the run stops for after its tool calls: an approval, or a question with options.
        self.waiting_for = {"tool": "bash", "command": "rm -rf build", "reason": "recursive delete"}
        self.bus = asyncio.Queue()
        self.runs = {}
        self.active_thread = "owner:abc"
        self.identity = FakeIdentity()
        self.language = FakeLanguage()
        self.skills = FakeSkills()
        self.jobs = FakeJobs()
        self.memory = FakeMemory(self.skills)
        self.usage = FakeUsage()
        self.channels = FakeChannels()
        self.email = FakeEmail()
        self.system = FakeSystem(self.bus)
        self.clients = FakeClients()
        self.conversations = FakeConversations()
        self.tasks = FakeTasks()
        self.devices = FakeDevices()
        self.logs = FakeLogs()
        self.files = FakeFiles()
        self.mcp = FakeMcp()
        self.home = FakeHome()
        self.repositories = FakeRepositories(self.skills, self.mcp)
        self.oauth = FakeOAuth(self.email, self.mcp)
        self.model = FakeModel()
        self.speech = FakeSpeech()
        self.web_search = FakeWebSearch()
        self.notifications = FakeNotifications()
        self.doctor = FakeDoctor()
        self.prompts = FakePrompts()
        # When set, the inbox sends the next message on there instead of running it.
        self.dispatch_to: Dispatched | None = None

    async def send(self, session, text, attachments=()):
        self.sent.append((text, [(a.name, a.media_type) for a in attachments]))
        if self.dispatch_to is not None:
            dispatched, self.dispatch_to = self.dispatch_to, None
            yield dispatched
            yield Done()
            return
        if any(a.media_type.startswith("audio/") for a in attachments):
            yield Transcribed("hola", "es")
        yield ToolStarted("bash", {"command": "ls -la"})
        yield ToolFinished("bash", "exit code: 0\nfile1")
        yield ToolStarted("bash", {"command": "rm -rf build"})
        yield ApprovalRequired("i1", self.waiting_for)

    async def resume(self, session, decisions):
        self.decisions = decisions
        yield ToolFinished("bash", "exit code: 0")
        for word in ["## Done\n\n", "Listed **1 file**."]:
            await asyncio.sleep(0)
            yield TextDelta(word)
        self.memory.profile = {"work": ["backend engineer"]}
        yield Done()

    async def move_dispatched(self, session, dispatch_id=""):
        self.sent.append((f"{session.thread_id} moves {dispatch_id}", []))
        if self.dispatch_to is not None:
            dispatched, self.dispatch_to = self.dispatch_to, None
            yield dispatched
        yield Done()

    async def send_dispatched(self, session, dispatch_id, text, brief=""):
        self.sent.append((f"{session.thread_id} ← {dispatch_id}", []))
        yield TextDelta("On it.")
        yield Done()

    async def inbox_thread(self, user_id):
        return "owner:abc"

    async def new_thread(self, user_id):
        return "owner:new"

    async def cancel(self, session):
        self.cancelled.append(session.thread_id)
        return True

    async def resume_thread(self, user_id, thread_id):
        if thread_id not in {c.thread_id for c in self.conversations.items}:
            raise ConversationError(f"No conversation {thread_id}.")
        self.active_thread = thread_id

    async def events(self, on_open=lambda: None, on_lost=lambda: None):
        """What the tests put on the bus; LOST and OPEN stand for the stream dropping and opening again."""
        on_open()
        while True:
            kind, data = await self.bus.get()
            if kind == LOST:
                on_lost()
            elif kind == OPEN:
                on_open()
            else:
                yield kind, data

    def follow_run(self, run_id):
        return self.runs[run_id]()


@pytest.fixture
def client():
    return FakeClient()


@pytest.fixture(autouse=True)
def english():
    """The app's text in English, as the tests expect it; a test that picks another language leaves it after."""
    i18n.use("en")
    yield
    i18n.use("en")


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
