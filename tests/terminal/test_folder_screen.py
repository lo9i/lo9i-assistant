"""/folder: the folder the conversation is handed to, with what changed there, or the home folder beside one that
isn't; a changed file opens on what changed, and a file goes to the trash once deleting is allowed."""

from rich.console import Group
from rich.syntax import Syntax
from textual.widgets import Button, Checkbox, OptionList, Static, Tree

from assistant.core.agent import FileChange, FolderEntry, Handoff
from assistant_terminal.folder_text import ChangeMarks, entry_label
from assistant_terminal.tui.screens import ConfirmScreen, FolderScreen
from tests.terminal.conftest import wait_for


def test_the_tree_marks_changes_and_strikes_what_was_deleted():
    marks = ChangeMarks(
        [FileChange("src/app.py", "modified"), FileChange("old.py", "deleted"), FileChange("docs/", "untracked")]
    )
    assert (marks.of("src", True), marks.of("src/app.py", False), marks.of("docs/a.md", False)) == (
        "inside",
        "modified",
        "untracked",
    )
    assert marks.file_change("src") is None and marks.file_change("old.py") == "deleted"
    label = entry_label(FolderEntry("old.py", "old.py", False, 0, True), "deleted")
    assert label.plain == "old.py D" and "strike" in str(label.style)


async def _open(app, pilot):
    await pilot.click("#prompt")
    await pilot.press(*"/folder", "enter")
    await wait_for(pilot, lambda: isinstance(app.screen, FolderScreen))
    return app.screen


def _shown(screen) -> str:
    """The text the file's view shows: a Syntax's code, a note's words."""
    content = screen.query_one("#folder-file", Static).content
    if isinstance(content, Group):
        content = content.renderables[-1]
    return content.code if isinstance(content, Syntax) else str(content)


async def test_the_handed_folder_shows_what_changed_and_a_changed_file_opens_on_its_diff(app, client):
    client.conversations.handoffs["owner:abc"] = Handoff("claude-code", "claude", "Claude Code", "/repo")
    async with app.run_test(size=(160, 48)) as pilot:
        screen = await _open(app, pilot)
        changes = screen.query_one("#folder-changes", OptionList)
        await wait_for(pilot, lambda: changes.option_count == 2)
        tree = screen.query_one("#folder-tree", Tree)
        labels = [str(n.label) for n in tree.root.children]
        assert labels == ["src/ •", "README.md D", "notes.txt"]  # what was deleted, where it was
        changes.highlighted = 0
        changes.action_select()
        await wait_for(pilot, lambda: "+new" in _shown(screen))
        assert screen.query_one("#view-text", Button).display
        screen.query_one("#view-text", Button).press()
        await wait_for(pilot, lambda: "print('hi')" in _shown(screen))
        changes.highlighted = 1
        changes.action_select()  # a deleted file: what changed only, nothing to show whole
        await wait_for(pilot, lambda: "-old" in _shown(screen))
        assert not screen.query_one("#view-text", Button).display


async def test_the_home_folder_has_no_changes_and_a_file_goes_to_the_trash_once_allowed(app, client):
    async with app.run_test(size=(160, 48)) as pilot:
        screen = await _open(app, pilot)
        assert not screen.query("#folder-changes")
        tree = screen.query_one("#folder-tree", Tree)
        await wait_for(pilot, lambda: [str(n.label) for n in tree.root.children] == ["todo.md"])
        tree.select_node(tree.root.children[0])
        await wait_for(pilot, lambda: "buy milk" in _shown(screen))
        trash = screen.query_one("#trash", Button)
        assert not trash.display  # deleting is off until turned on
        screen.query_one("#allow-deleting", Checkbox).value = True
        await wait_for(pilot, lambda: client.folders.deleting_on and trash.display)
        trash.press()
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmScreen))
        await pilot.press("y")
        await wait_for(pilot, lambda: client.folders.home_folder.deleted == ["todo.md"])
        await wait_for(pilot, lambda: not tree.root.children or str(tree.root.children[0].label) != "todo.md")
