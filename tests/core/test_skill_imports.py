from pathlib import Path

import pytest

from assistant.core.events import ApprovalRequired, ToolFinished
from assistant.core.skills import store
from assistant.core.skills.imports import formats, importing, listing, setup
from tests.conftest import collect


def _skill(folder: Path, header: str, body: str, files: dict[str, str] | None = None) -> Path:
    folder.mkdir(parents=True)
    (folder / "SKILL.md").write_text(f"---\n{header}\n---\n\n{body}\n", encoding="utf-8")
    for path, content in (files or {}).items():
        (folder / path).parent.mkdir(parents=True, exist_ok=True)
        (folder / path).write_text(content, encoding="utf-8")
    return folder


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    return home


@pytest.fixture
def pdf(home: Path) -> Path:
    return _skill(
        home / ".claude" / "skills" / "pdf",
        "name: pdf\ndescription: Fill PDF forms",
        "Run `python ${CLAUDE_SKILL_DIR}/scripts/fill.py` on the form.",
        {"scripts/fill.py": "print('filled')"},
    )


def _by_name(home: Path, projects: list[Path] | None = None) -> dict[str, listing.Importable]:
    return {i.name: i for i in listing.listing(home, projects or []).skills}


def test_skills_and_prompts_are_found_where_each_agent_keeps_them(home: Path, pdf: Path, tmp_path: Path):
    _skill(home / ".agents" / "skills" / "review", "name: review\ndescription: Review a change", "Look at the diff.")
    _skill(home / ".codex" / "skills" / ".system" / "plan", "name: plan\ndescription: Codex's own", "Plan.")
    (home / ".codex" / "prompts").mkdir(parents=True)
    (home / ".codex" / "prompts" / "Release Notes.md").write_text("Write release notes for $1.\n")
    project = tmp_path / "project"
    _skill(project / ".claude" / "skills" / "deploy", "name: deploy\ndescription: Deploy it", "Deploy.")
    (project / "AGENTS.md").write_text("Use uv.")
    (home / ".claude" / "CLAUDE.md").write_text("Be brief.")

    found = listing.listing(home, [project, home])

    assert [(i.name, i.agent_name, i.kind, i.project) for i in found.skills] == [
        ("pdf", "Claude Code", "skills", ""),
        ("review", "Codex", "skills", ""),
        ("release-notes", "Codex", "prompts", ""),
        ("deploy", "Claude Code", "skills", str(project)),
    ]
    assert {i.state for i in found.skills} == {listing.NEW}
    assert found.suggestions == [str(home / ".claude" / "CLAUDE.md"), str(project / "AGENTS.md")]
    prompt = _by_name(home)["release-notes"]
    assert prompt.description == "Write release notes for $1." and prompt.id.endswith("Release Notes.md")


def test_formats_map_to_the_assistants_skills():
    instructions = formats.skill_instructions("Run ${CLAUDE_SKILL_DIR}/scripts/a.py with $ARGUMENTS.", "Claude Code")
    assert "Run scripts/a.py with $ARGUMENTS." in instructions
    assert instructions.startswith("(Written for Claude Code, where $ARGUMENTS stand for what the user typed")
    prompt = formats.prompt_instructions("Fix $TICKET, costs $$5.", {"argument-hint": "TICKET=<id>"})
    assert "$TICKET" in prompt and "It takes: TICKET=<id>." in prompt and prompt.endswith("Fix $TICKET, costs $5.")
    assert formats.skill_instructions("No placeholders here.", "Codex") == "No placeholders here."
    assert formats.description({}, "# Commit helper\n\nMore.") == "Commit helper"
    assert formats.name("My PDF_Tool!") == "my-pdf-tool"


def test_what_needs_a_coding_agents_own_tools_is_flagged():
    meta = {"allowed-tools": ["Bash(git *)", "Edit"], "context": "fork"}
    reasons = formats.needs_agent(meta, "Use the `Edit` tool, then !`git status`.", "Claude Code")
    assert reasons == [
        "Its header gives it Claude Code's tools: Bash(git *), Edit.",
        "It runs as a Claude Code subagent.",
        "It runs commands as Claude Code loads it (!`…`); here they're only text.",
        "It uses a coding agent's tools: Edit.",
    ]
    assert formats.needs_agent({}, "Read the report and write a summary. Then apply_patch.", "Codex") == [
        "It uses a coding agent's tools: apply_patch."
    ]
    assert formats.needs_agent({}, "Read the report and write a summary.", "Codex") == []


def test_a_skill_is_copied_with_its_files_and_where_it_came_from(home: Path, pdf: Path):
    item = _by_name(home)["pdf"]

    [outcome] = importing.import_skills([item.id], False, home, [])

    assert (outcome.action, outcome.name) == (importing.IMPORTED, "pdf")
    skill = store.load("pdf")
    assert skill.description == "Fill PDF forms" and "python scripts/fill.py" in skill.instructions
    assert skill.files == ["scripts/fill.py"] and not skill.problems and not skill.plugin
    assert skill.imported_from == str(pdf)
    copied = store.folder("pdf")
    assert not copied.is_symlink() and not (copied / "scripts" / "fill.py").is_symlink()
    assert _by_name(home)["pdf"].state == listing.IMPORTED


def test_a_name_clash_gets_the_agents_name_unless_told_to_replace(home: Path, pdf: Path):
    store.save("pdf", "My own PDF skill", "Mine.")
    _skill(home / ".agents" / "skills" / "pdf", "name: pdf\ndescription: Codex's PDF", "Theirs.")
    _skill(home / ".agents" / "skills" / "assistant-setup", "name: assistant-setup\ndescription: x", "x")
    found = {i.id: i for i in listing.listing(home, []).skills}
    assert (found[str(pdf)].name_here, found[str(pdf)].renamed) == (
        "pdf-claude",
        "named pdf-claude: you already have a skill named pdf",
    )

    claude_pdf = str(pdf)
    codex_pdf = str(home / ".agents" / "skills" / "pdf")
    setup_id = str(home / ".agents" / "skills" / "assistant-setup")
    outcomes = importing.import_skills([claude_pdf, codex_pdf, setup_id], False, home, [])
    assert [o.name for o in outcomes] == ["pdf-claude", "pdf-codex", "assistant-setup-codex"]
    assert store.load("pdf").instructions == "Mine."

    store.delete("pdf-claude")
    replaced = importing.import_skills([claude_pdf, setup_id], True, home, [])
    assert [(o.name, o.note) for o in replaced] == [("pdf", "replaces your skill pdf"), ("assistant-setup-codex", "")]
    assert store.load("pdf").description == "Fill PDF forms"
    assert store.load("assistant-setup").builtin


def test_a_changed_source_is_marked_and_updated_only_when_imported_again(home: Path, pdf: Path):
    importing.import_skills([str(pdf)], False, home, [])
    (pdf / "scripts" / "fill.py").write_text("print('filled better')")

    assert _by_name(home)["pdf"].state == listing.CHANGED
    assert (store.folder("pdf") / "scripts" / "fill.py").read_text() == "print('filled')"

    [outcome] = importing.import_skills([str(pdf)], False, home, [])
    assert (outcome.action, outcome.name) == (importing.UPDATED, "pdf")
    assert (store.folder("pdf") / "scripts" / "fill.py").read_text() == "print('filled better')"
    assert _by_name(home)["pdf"].state == listing.IMPORTED


def test_a_skill_with_problems_or_gone_isnt_imported(home: Path):
    broken = _skill(home / ".claude" / "skills" / "report", "name: report", "Run scripts/report.py.")
    assert _by_name(home)["report"].problems == ["Its instructions use files it doesn't have: scripts/report.py."]
    outcomes = importing.import_skills([str(broken), str(home / "gone")], False, home, [])
    assert [o.action for o in outcomes] == [importing.FAILED, importing.FAILED]
    assert "list them again" in outcomes[1].note
    assert store.saved_skills() == []


def test_install_asks_once_and_all_leaves_out_skills_for_coding_agents(home: Path, pdf: Path):
    _skill(home / ".agents" / "skills" / "edit", "name: edit\ndescription: Edit files", "Use the `Edit` tool.")
    asked: list[str] = []

    setup.main(lambda q: asked.append(q) or "a", home)
    setup.main(lambda q: asked.append(q) or "a", home)

    assert len(asked) == 1
    assert [s.name for s in store.saved_skills()] == ["pdf"]


def test_install_picks_by_number_and_asks_nothing_when_none_is_found(home: Path, pdf: Path, capsys):
    _skill(home / ".agents" / "skills" / "edit", "name: edit\ndescription: Edit files", "Use the `Edit` tool.")
    answers = iter(["p", "2"])

    setup.main(lambda _: next(answers), home)

    assert "Found 1 skill from Claude Code and 1 skill from Codex" in capsys.readouterr().out
    assert [s.name for s in store.saved_skills()] == ["edit"]


def test_install_asks_nothing_without_skills_to_import(home: Path):
    setup.main(lambda _: pytest.fail("asked"), home)


async def test_the_assistant_lists_them_and_imports_what_the_user_approves(service, script, home: Path, pdf: Path):
    script.call("list_importable_skills").call("import_skills", ids=[str(pdf)]).reply("Imported pdf.")
    session = await service.session("owner", "cli")

    asked = await collect(service.send(session, "bring my Claude Code skills over"))
    approval = next(e for e in asked if isinstance(e, ApprovalRequired))
    assert approval.request["tool"] == "import_skills" and f"pdf ← {pdf}" in approval.request["command"]
    resumed = await collect(service.resume(session, {approval.interrupt_id: {"approved": True}}))

    [listed] = [e.output for e in asked if isinstance(e, ToolFinished)]
    [imported] = [e.output for e in resumed if isinstance(e, ToolFinished)]
    assert f"- id {pdf}: pdf (Claude Code): Fill PDF forms [new]" in listed
    assert imported == f"- {pdf}: imported pdf"
    assert store.load("pdf").files == ["scripts/fill.py"]
