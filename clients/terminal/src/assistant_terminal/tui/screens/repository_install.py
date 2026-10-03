"""Installing skills and MCP servers from a git repository: its address, a look at what it offers,
then the ones to install, with the values each server asks for (secrets are typed here and go
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

_INTRO = """## Install from a repository

Skills and MCP servers from a git repository's https:// address. What you install runs on the
computer running the assistant, so install only from people you trust."""

_SKILL, _SERVER = "skill:", "server:"


class RepositoryInstallScreen(ModalScreen[list[str]]):
    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "dismiss([])", "Close")]

    def __init__(self, repositories: RepositoriesApi) -> None:
        super().__init__()
        self._repositories = repositories
        self._servers: dict[str, FoundServer] = {}
        # One input per field of each server, by server name and field key.
        self._inputs: dict[str, dict[str, Input]] = {}

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="repository-install"):
            yield Markdown(_INTRO)
            yield Input(placeholder="https://github.com/user/extras", id="repository-url")
            yield Markdown(id="repository-message")
            yield SelectionList[str](id="repository-found")
            yield Vertical(id="repository-fields")
            with Horizontal(id="repository-buttons"):
                yield Button("Look", variant="primary", id="browse")
                yield Button("Install", variant="success", id="install")
                yield Button("Cancel", id="cancel")

    def on_mount(self) -> None:
        self._show_choice(False)

    @on(Button.Pressed, "#cancel")
    def _cancel(self) -> None:
        self.dismiss([])

    @on(Input.Changed, "#repository-url")
    def _url_changed(self) -> None:
        self._show_choice(False)

    @on(Button.Pressed, "#browse")
    @on(Input.Submitted, "#repository-url")
    @reports_daemon_unavailable
    async def _browse(self) -> None:
        await self._say("Downloading…")
        try:
            contents = await self._repositories.browse(self._url())
        except RepositoryError as e:
            await self._say(f"**{e}**")
            return
        await self._show(contents)

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
            await self._repositories.install(self._url(), skills, wanted)
        except RepositoryError as e:
            await self._say(f"**{e}**")
            return
        self.dismiss([*skills, *servers])

    async def _show(self, contents: RepositoryContents) -> None:
        self._servers = {s.name: s for s in contents.servers}
        found = self.query_one("#repository-found", SelectionList)
        found.clear_options()
        only_one = len(contents.skills) + len(contents.servers) == 1
        found.add_options([(_skill_label(s), _SKILL + s.name, only_one) for s in contents.skills])
        found.add_options([(_server_label(s), _SERVER + s.name, only_one) for s in contents.servers])
        await self._mount_fields(contents.servers)
        self._show_choice(True)
        self._selection_changed()
        await self._say("Check what to install. Servers ask for their values below, then Install.")

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

    def _url(self) -> str:
        return self.query_one("#repository-url", Input).value.strip()

    async def _say(self, text: str) -> None:
        await self.query_one("#repository-message", Markdown).update(text)


def _field_input(server: FoundServer, field: ServerField) -> Input:
    hint = f" ({field.help})" if field.help else ""
    return Input(placeholder=f"{server.name}: {field.label}{hint}", password=field.secret)


def _skill_label(skill: FoundSkill) -> str:
    files = f", {len(skill.files)} files" if skill.files else ""
    return f"Skill {skill.name}{files}: {skill.description}"


def _server_label(server: FoundServer) -> str:
    kind = "local" if server.transport == "stdio" else "remote"
    return f"MCP server {server.name} ({kind}): {server.description}"
