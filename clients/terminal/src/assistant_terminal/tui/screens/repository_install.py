"""Installing plugins (MCP servers and skills) from the assistant's extras: a look at what they
offer, then the ones to install, with the values each server asks for (secrets are typed here and go
straight to the daemon). Returns the names installed, or an empty list."""

from typing import ClassVar

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Markdown, SelectionList

from assistant.client.daemon_client import RepositoriesApi
from assistant.core.agent import FoundServer, FoundSkill, RepositoryContents, RepositoryError, ServerField, ServerValues
from assistant_terminal.tui.daemon_errors import reports_daemon_unavailable

_INTRO = """## Install a plugin

MCP servers, chat channels and skills from the assistant's extras. What you install runs on the
computer running the assistant."""

_SKILL, _SERVER = "skill:", "server:"


class RepositoryInstallScreen(ModalScreen[list[str]]):
    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "dismiss([])", "Close")]

    def __init__(
        self,
        repositories: RepositoriesApi,
        kind: str = "",
        only: str = "",
        offered: FoundServer | FoundSkill | None = None,
    ) -> None:
        """`kind`: only "server"s (from /mcp) or only "skill"s (from /skills). `only`: just this plugin,
        to give the values it asks for (from /plugins). `offered`: a plugin the agent offers in the
        chat, already read from the extras. What's installed already isn't offered."""
        super().__init__()
        self._repositories = repositories
        self._kind, self._only = kind, only
        self._offer = offered
        self._servers: dict[str, FoundServer] = {}
        # One input per field of each server, by server name and field key.
        self._inputs: dict[str, dict[str, Input]] = {}

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="repository-install"):
            yield Markdown(_offer_intro(self._offer) if self._offer else _INTRO)
            yield Markdown(id="repository-message")
            yield SelectionList[str](id="repository-found")
            yield Vertical(id="repository-fields")
            with Horizontal(id="repository-buttons"):
                yield Button("Install", variant="success", id="install")
                yield Button("Cancel", id="cancel")

    async def on_mount(self) -> None:
        self._show_choice(False)
        if self._offer is None:
            await self._browse()
            return
        offer = self._offer
        await self._show(
            RepositoryContents([], [offer]) if isinstance(offer, FoundServer) else RepositoryContents([offer], [])
        )

    @on(Button.Pressed, "#cancel")
    def _cancel(self) -> None:
        self.dismiss([])

    @reports_daemon_unavailable
    async def _browse(self) -> None:
        await self._say("Looking at the extras…")
        try:
            contents = await self._repositories.browse()
        except RepositoryError as e:
            await self._say(f"**{e}**")
            return
        await self._show(self._offered(contents))

    def _offered(self, contents: RepositoryContents) -> RepositoryContents:
        def offered(kind: str, name: str, installed: bool) -> bool:
            return not installed and self._kind in ("", kind) and self._only in ("", name)

        return RepositoryContents(
            [s for s in contents.skills if offered("skill", s.name, s.installed)],
            [s for s in contents.servers if offered("server", s.name, s.installed) and self._offers_server(s)],
        )

    def _offers_server(self, server: FoundServer) -> bool:
        """/mcp lists servers with tools: a plugin without them is installed from /plugins."""
        return not (self._kind == "server" and server.transport == "none")

    @on(SelectionList.SelectedChanged, "#repository-found")
    def _selection_changed(self) -> None:
        chosen = self._chosen(_SERVER)
        for name, inputs in self._inputs.items():
            for field_input in inputs.values():
                field_input.display = name in chosen

    @on(Button.Pressed, "#install")
    @reports_daemon_unavailable
    async def _install(self) -> None:
        skills, servers = self._chosen(_SKILL), self._chosen(_SERVER)
        wanted = [ServerValues(name, {k: i.value.strip() for k, i in self._inputs[name].items()}) for name in servers]
        try:
            await self._repositories.install(skills, wanted)
        except RepositoryError as e:
            await self._say(f"**{e}**")
            return
        self.dismiss([*skills, *servers])

    async def _show(self, contents: RepositoryContents) -> None:
        self._servers = {s.name: s for s in contents.servers}
        found = self.query_one("#repository-found", SelectionList)
        found.clear_options()
        if not contents.skills and not contents.servers:
            await self._say("Everything the extras offer here is installed already.")
            return
        only_one = len(contents.skills) + len(contents.servers) == 1
        found.add_options([(_skill_label(s), _SKILL + s.name, only_one) for s in contents.skills])
        found.add_options([(_server_label(s), _SERVER + s.name, only_one) for s in contents.servers])
        await self._mount_fields(contents.servers)
        self._show_choice(True)
        self._selection_changed()
        await self._say(_guide(contents))

    async def _mount_fields(self, servers: list[FoundServer]) -> None:
        box = self.query_one("#repository-fields", Vertical)
        await box.remove_children()
        self._inputs = {s.name: {f.key: _field_input(s, f) for f in s.fields} for s in servers}
        await box.mount_all([i for inputs in self._inputs.values() for i in inputs.values()])

    def _chosen(self, kind: str) -> list[str]:
        selected = self.query_one("#repository-found", SelectionList).selected
        return [str(v).removeprefix(kind) for v in selected if str(v).startswith(kind)]

    def _show_choice(self, shown: bool) -> None:
        for widget in ("#repository-found", "#repository-fields", "#install"):
            self.query_one(widget).display = shown

    async def _say(self, text: str) -> None:
        await self.query_one("#repository-message", Markdown).update(text)


def _guide(contents: RepositoryContents) -> str:
    """What to do: a single plugin's steps for what it asks for, numbered, when it has them."""
    steps = contents.servers[0].steps if len(contents.servers) == 1 and not contents.skills else []
    if steps:
        return "\n".join(f"{i}. {step}" for i, step in enumerate(steps, 1))
    return "Check what to install. Servers ask for their values below, then Install."


def _offer_intro(plugin: FoundServer | FoundSkill) -> str:
    return f"## Install {plugin.name}\n\nThe assistant offers it: {plugin.description}"


# For a field the daemon already has a value for, from before channels were plugins.
_KNOWN_HINT = "leave empty to keep the one you set before"


def _field_input(server: FoundServer, field: ServerField) -> Input:
    hints = [*([field.help] if field.help else []), *([_KNOWN_HINT] if field.key in server.known_fields else [])]
    hint = f" ({'; '.join(hints)})" if hints else ""
    return Input(placeholder=f"{server.name}: {field.label}{hint}", password=field.secret)


def _skill_label(skill: FoundSkill) -> str:
    files = f", {len(skill.files)} files" if skill.files else ""
    return f"Skill {skill.name}{files}: {skill.description}"


def _server_label(server: FoundServer) -> str:
    if server.transport == "none":
        return f"{'Email provider' if server.email else 'Channel'} {server.name}: {server.description}"
    extras = ["remote" if server.transport == "http" else "local"]
    pairs = (("a chat channel", server.channel), ("with its skill", server.skill), ("with a web page", server.page))
    extras += [e for e, has in pairs if has]
    return f"MCP server {server.name} ({', '.join(extras)}): {server.description}"
