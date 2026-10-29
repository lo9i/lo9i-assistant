"""Repositories: where Plugins lists plugins from. The assistant's extras are built in and official;
the user adds others by their https:// address, a private one with a token that can read it (typed
here, it goes straight to the daemon), and removes them, as in the web app's Repositories dialog on
Plugins. Removing one leaves what was installed from it."""

from typing import ClassVar

from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, OptionList, Static
from textual.widgets.option_list import Option

from assistant.client.daemon_client import RepositoriesApi
from assistant.core.agent import Repository, RepositoryError
from assistant_terminal.i18n import t
from assistant_terminal.tui.daemon_errors import reports_daemon_unavailable
from assistant_terminal.tui.screens.confirm import ConfirmScreen


class RepositoriesScreen(ModalScreen[None]):
    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "dismiss", t("Close"))]

    def __init__(self, repositories: RepositoriesApi) -> None:
        super().__init__()
        self._repositories = repositories
        self._listed: list[Repository] = []

    def compose(self) -> ComposeResult:
        with Vertical(id="repositories"):
            yield Static(t("Repositories Plugins lists plugins from. Only the assistant's extras are official."))
            yield OptionList(id="repositories-list")
            yield Input(placeholder=t("https://github.com/you/your-plugins"), id="repository-url")
            yield Input(placeholder=t("Token, for a private repository"), password=True, id="repository-token")
            yield Static(
                t(
                    "Git repositories by their https:// address. For a private one, a token that can read its contents"
                    " (on GitHub, a fine-grained token with Contents: read). What you install from one runs on this"
                    " computer."
                ),
                classes="hint",
            )
            with Horizontal(id="repositories-buttons"):
                yield Button(t("Add"), variant="success", id="add")
                yield Button(t("Remove"), variant="error", id="remove")
                yield Button(t("Close (esc)"), id="close")

    @reports_daemon_unavailable
    async def on_mount(self) -> None:
        await self._list()

    async def _list(self) -> None:
        self._listed = await self._repositories.list()
        options = self.query_one("#repositories-list", OptionList)
        options.clear_options()
        options.add_options([Option(_label(r), id=r.url) for r in self._listed])
        self._show_remove()

    @on(OptionList.OptionHighlighted)
    def _show_remove(self) -> None:
        """The extras can't be removed."""
        self.query_one("#remove").display = not getattr(self._highlighted(), "official", True)

    def _highlighted(self) -> Repository | None:
        index = self.query_one("#repositories-list", OptionList).highlighted
        return self._listed[index] if index is not None and index < len(self._listed) else None

    @on(Button.Pressed, "#add")
    @on(Input.Submitted, "#repository-url")
    @on(Input.Submitted, "#repository-token")
    @reports_daemon_unavailable
    async def _add(self) -> None:
        field, token = self.query_one("#repository-url", Input), self.query_one("#repository-token", Input)
        if not field.value.strip():
            return
        self.notify(t("Reading the repository…"))
        try:
            added = await self._repositories.add(field.value, token.value.strip())
        except RepositoryError as e:
            self.notify(str(e), severity="error", timeout=10)
            return
        field.value = token.value = ""
        self.notify(t("Added {name}. Its plugins show in Plugins.", name=added.name))
        await self._list()

    @on(Button.Pressed, "#remove")
    @work
    @reports_daemon_unavailable
    async def _remove(self) -> None:
        repository = self._highlighted()
        if repository is None or repository.official:
            return
        question = t(
            "Remove {name}? Plugins installed from it stay installed and keep updating from it.", name=repository.name
        )
        if repository.private:
            question += " " + t("Its token stays until you remove the last of them.")
        if not await self.app.push_screen_wait(ConfirmScreen(question, t("Remove"))):
            return
        try:
            await self._repositories.remove(repository.url)
        except RepositoryError as e:
            self.notify(str(e), severity="error")
        await self._list()

    @on(Button.Pressed, "#close")
    def _close(self) -> None:
        self.dismiss()


def _label(repository: Repository) -> str:
    return (
        f"{repository.name}  [b]{t('Official')}[/b]"
        if repository.official
        else f"{repository.name}  [dim]{repository.url}[/dim]"
    )
