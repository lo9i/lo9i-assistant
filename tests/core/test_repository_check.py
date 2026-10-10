"""Checking a plugin repository the way lo9i reads it, before it's pushed (core/repositories/check.py)."""

from pathlib import Path

from assistant.core.repositories.check import problems


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def test_a_repository_lo9i_reads_whole_has_no_problems(tmp_path):
    _write(tmp_path / "apps" / "finance" / "ledger" / "server.yaml", 'description: "Money: in and out"\ncommand: x')
    _write(tmp_path / "assistant" / "modes" / "coder" / "SKILL.md", "---\nname: coder\ndescription: Code\n---\n\nDo.")
    _write(tmp_path / "apps" / "finance" / "ledger" / ".venv" / "lib" / "server.yaml", "not: [a plugin")
    assert problems(tmp_path) == []


def test_a_server_yaml_that_isnt_yaml_is_named(tmp_path):
    _write(tmp_path / "apps" / "finance" / "ledger" / "server.yaml", "description: Money: in and out\ncommand: x")
    [problem] = problems(tmp_path)
    assert problem.startswith("apps/finance/ledger/server.yaml can't be used: mapping values are not allowed")


def test_a_plugin_outside_the_category_folders_is_named(tmp_path):
    _write(tmp_path / "productivity" / "notes" / "notes" / "server.yaml", "command: x")
    [problem] = problems(tmp_path)
    assert problem.startswith("productivity/notes/notes: lo9i doesn't look in this folder")


def test_a_skill_with_problems_is_named(tmp_path):
    _write(tmp_path / "assistant" / "modes" / "coder" / "SKILL.md", "---\nname: coder\ncategory: nope/nope\n---\n\nDo.")
    [problem] = problems(tmp_path)
    assert problem.startswith("assistant/modes/coder/SKILL.md: ")
