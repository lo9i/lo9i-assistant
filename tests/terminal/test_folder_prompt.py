"""The plain REPL's folder picker for /claude alone: the workspace, the folders used before, or browsing to one,
hidden folders only after Show hidden, as the full app's picker."""

from assistant_terminal.folder_prompt import FolderPrompt


def _answers(*lines: str):
    """Reads `lines` one by one, then the end of input."""
    queued = list(lines)

    async def read(prompt: str) -> str | None:
        return queued.pop(0) if queued else None

    return read


async def _pick(client, *lines: str) -> str | None:
    read = _answers(*lines)
    return await FolderPrompt(client.conversations, read).pick("Claude Code")


async def test_a_folder_used_before_is_picked_by_its_number(client, capsys):
    assert await _pick(client, "2") == "/home/me/projects/app"
    shown = capsys.readouterr().out
    assert "1. /home/me/.lo9i/claude-workspace (workspace)" in shown and "3. Browse…" in shown


async def test_browsing_goes_into_a_folder_and_picks_it(client, capsys):
    # Browse… from home, then projects/, then new/, then Use this folder.
    assert await _pick(client, "3", "4", "5", "1") == "/home/me/projects/new"
    shown = capsys.readouterr().out
    assert "1. Use this folder\n  2. .. up\n  3. Show hidden\n  4. projects/" in shown


async def test_up_goes_to_the_parent_folder(client):
    assert await _pick(client, "3", "4", "2", "1") == "/home/me"


async def test_hidden_folders_show_only_after_show_hidden(client, capsys):
    assert await _pick(client, "3", "3", "4") is None  # 4 is .config/ now: browsing it, then the input ends
    shown = capsys.readouterr().out
    assert "4. projects/" in shown and "3. Hide hidden\n  4. .config/\n  5. projects/" in shown


async def test_a_full_path_is_taken_as_it_is_and_nothing_cancels(client):
    assert await _pick(client, "/tmp/repo") == "/tmp/repo"
    assert await _pick(client, "") is None
    assert await _pick(client, "3", "") is None
