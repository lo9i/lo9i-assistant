"""/folder: the folder panel's folder, as the web app shows it beside a conversation: the one it's handed to, with
what git says changed (listed at the top and marked in the tree, what was deleted struck through where it was), or
the home folder beside one that isn't. A file opens beside the tree: what changed in it when git lists it, its whole
text a key away, or its text otherwise. A file can be moved to the system's trash, once the user confirms, while
deleting is allowed (off until turned on, here or in the web app's Settings → General). Read again after each step the
agent reports and when it's done, and on Refresh."""

from typing import ClassVar

from rich.console import Group, RenderableType
from rich.syntax import Syntax
from rich.text import Text
from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Checkbox, OptionList, Static, Tree
from textual.widgets.option_list import Option
from textual.widgets.tree import TreeNode

from assistant.client.daemon_client import FoldersApi, ShownFolder
from assistant.core.agent import FileChange, FolderEntry, HandedFolderError
from assistant_terminal.folder_text import CHANGES, WHOLE_FILE, ChangeMarks, change_label, entry_label
from assistant_terminal.i18n import t, translatable
from assistant_terminal.tui.daemon_errors import reports_daemon_unavailable
from assistant_terminal.tui.screens.confirm import ConfirmScreen

_PICK = translatable("Pick a file to see it here.")
_NOT_TEXT = translatable("Can't be previewed: it isn't a text file.")
_DIFF_NOT_TEXT = translatable("Can't show what changed: it isn't a text file.")
_TRUNCATED = translatable("Too big to show whole: this is its start.")
_THEME = "ansi_dark"


class FolderScreen(ModalScreen[None]):
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "dismiss", t("Close")),
        Binding("r", "reload", t("Refresh")),
    ]
    RELOADS_ON: ClassVar[frozenset[str]] = frozenset({"agent_task_progress", "agent_finished", "settings"})

    def __init__(self, folder: ShownFolder, folders: FoldersApi, title: str) -> None:
        super().__init__()
        self._folder = folder
        self._folders = folders
        self._title = title
        self._marks = ChangeMarks([])
        # The folders listed so far, by path, and the file shown with how ("diff" or "text").
        self._listed: set[str] = set()
        self._shown: str | None = None
        self._view = "text"
        self._deleting = False

    def compose(self) -> ComposeResult:
        with Vertical(id="folder"):
            yield Static(self._title, id="folder-title", markup=False)
            with Horizontal(id="folder-main"):
                with Vertical(id="folder-side"):
                    if self._folder.has_changes:
                        yield Static(t("Changed"), id="folder-changed-title")
                        yield OptionList(id="folder-changes")
                    yield Tree[FolderEntry | None](self._title, data=None, id="folder-tree")
                with VerticalScroll(id="folder-view"):
                    yield Static(id="folder-file-title", markup=False)
                    yield Static(t(_PICK), id="folder-file")
            with Horizontal(id="folder-buttons"):
                yield Button(t(CHANGES), id="view-diff")
                yield Button(t(WHOLE_FILE), id="view-text")
                yield Button(t("Move to trash"), variant="error", id="trash")
                yield Checkbox(t("Allow deleting files"), id="allow-deleting")
                yield Button(t("Refresh"), id="refresh")
                yield Button(t("Close"), id="close")

    @reports_daemon_unavailable
    async def on_mount(self) -> None:
        self.query_one("#folder-tree", Tree).root.expand()
        await self.reload()

    @reports_daemon_unavailable
    async def reload(self) -> None:
        """The folder, its changes, the open folders and the file shown, read again; and whether deleting is on."""
        await self._read_changes()
        tree = self.query_one("#folder-tree", Tree)
        opened = {n.data.path for n in _nodes(tree.root) if n.data is not None and n.is_expanded}
        self._listed.clear()
        await self._fill(tree.root, "", opened)
        self._deleting = await self._folders.deleting()
        self.query_one("#allow-deleting", Checkbox).value = self._deleting
        if self._shown is not None:
            await self._show()
        self._update_buttons()

    async def action_reload(self) -> None:
        await self.reload()

    async def _read_changes(self) -> None:
        try:
            found = await self._folder.changes()
        except HandedFolderError as e:
            self.notify(str(e), severity="error")
            found = None
        listed: list[FileChange] = found.changes if found else []
        self._marks = ChangeMarks(listed)
        if self._folder.has_changes:
            options = self.query_one("#folder-changes", OptionList)
            options.clear_options()
            options.add_options([Option(change_label(c), id=c.path) for c in listed])
            if found is not None and not found.repository:
                options.add_option(Option(t("Not a git repository: changes aren't tracked."), disabled=True))
            elif not listed:
                options.add_option(Option(t("Nothing changed."), disabled=True))

    async def _fill(self, node: TreeNode[FolderEntry | None], path: str, opened: set[str]) -> None:
        """Lists `path` under `node`, then the folders in it that were open, open again."""
        node.remove_children()
        self._listed.add(path)
        try:
            listing = await self._folder.contents(path)
        except HandedFolderError as e:
            node.add_leaf(Text(str(e), style="red"))
            return
        for entry in listing.entries:
            label = entry_label(entry, self._marks.of(entry.path, entry.folder))
            if not entry.folder:
                node.add_leaf(label, data=entry)
                continue
            child = node.add(label, data=entry, allow_expand=True)
            if entry.path in opened:
                await self._fill(child, entry.path, opened)
                child.expand()
        if listing.truncated:
            node.add_leaf(t("More files than shown."))
        if not listing.entries:
            node.add_leaf(Text(t("Empty folder."), style="dim"))

    @on(Tree.NodeExpanded, "#folder-tree")
    @reports_daemon_unavailable
    async def _opened(self, event: Tree.NodeExpanded[FolderEntry | None]) -> None:
        entry = event.node.data
        if entry is not None and entry.folder and entry.path not in self._listed:
            await self._fill(event.node, entry.path, set())

    @on(Tree.NodeSelected, "#folder-tree")
    @reports_daemon_unavailable
    async def _tree_picked(self, event: Tree.NodeSelected[FolderEntry | None]) -> None:
        entry = event.node.data
        if entry is not None and not entry.folder:
            await self._pick(entry.path)

    @on(OptionList.OptionSelected, "#folder-changes")
    @reports_daemon_unavailable
    async def _change_picked(self, event: OptionList.OptionSelected) -> None:
        path = event.option.id
        if path and not path.endswith("/"):
            await self._pick(path)

    async def _pick(self, path: str) -> None:
        self._shown = path
        self._view = "diff" if self._change() else "text"
        await self._show()

    def _change(self) -> str | None:
        if self._shown is None or not self._folder.has_changes:
            return None
        return self._marks.file_change(self._shown)

    async def _show(self) -> None:
        """The file shown, read again as it's shown: what changed in it, or its text."""
        path = self._shown
        if path is None:
            return
        self.query_one("#folder-file-title", Static).update(path)
        body: RenderableType
        try:
            body = await (self._diff(path) if self._view == "diff" else self._text(path))
        except HandedFolderError as e:
            body = Text(str(e), style="red")
        self.query_one("#folder-file", Static).update(body)
        self._update_buttons()

    async def _diff(self, path: str) -> RenderableType:
        found = await self._folder.diff(path)
        if found.text is None:
            return Text(t(_DIFF_NOT_TEXT), style="dim")
        return _with_note(Syntax(found.text, "diff", theme=_THEME), found.truncated)

    async def _text(self, path: str) -> RenderableType:
        found = await self._folder.file(path)
        if found.text is None:
            return Text(t(_NOT_TEXT), style="dim")
        lexer = Syntax.guess_lexer(path, found.text)
        return _with_note(Syntax(found.text, lexer, theme=_THEME), found.truncated)

    def _update_buttons(self) -> None:
        change = self._change()
        there = self._shown is not None and change != "deleted"
        for button, view in (("#view-diff", "diff"), ("#view-text", "text")):
            shown = self.query_one(button, Button)
            shown.display = change is not None and there
            shown.variant = "primary" if self._view == view else "default"
        self.query_one("#trash", Button).display = there and self._deleting

    @on(Button.Pressed, "#view-diff")
    @reports_daemon_unavailable
    async def _show_diff(self) -> None:
        self._view = "diff"
        await self._show()

    @on(Button.Pressed, "#view-text")
    @reports_daemon_unavailable
    async def _show_text(self) -> None:
        self._view = "text"
        await self._show()

    @on(Checkbox.Changed, "#allow-deleting")
    @reports_daemon_unavailable
    async def _allow_deleting(self, event: Checkbox.Changed) -> None:
        if event.value != self._deleting:
            self._deleting = await self._folders.set_deleting(event.value)
            self._update_buttons()

    @on(Button.Pressed, "#trash")
    @work
    @reports_daemon_unavailable
    async def _trash(self) -> None:
        path = self._shown
        question = t("Move {path} to the trash? You can take it back from there.", path=path)
        if path is None or not await self.app.push_screen_wait(ConfirmScreen(question, t("Move to trash"))):
            return
        try:
            await self._folder.delete(path)
        except HandedFolderError as e:
            self.notify(str(e), severity="error")
            return
        self._shown = None
        self.query_one("#folder-file-title", Static).update("")
        self.query_one("#folder-file", Static).update(t(_PICK))
        await self.reload()

    @on(Button.Pressed, "#refresh")
    async def _refresh(self) -> None:
        await self.reload()

    @on(Button.Pressed, "#close")
    def _close(self) -> None:
        self.dismiss()


def _nodes(node: TreeNode[FolderEntry | None]) -> list[TreeNode[FolderEntry | None]]:
    return [node, *(n for child in node.children for n in _nodes(child))]


def _with_note(body: Syntax, truncated: bool) -> RenderableType:
    return Group(Text(t(_TRUNCATED), style="dim"), body) if truncated else body
