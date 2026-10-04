import sys

import pytest

from assistant.core.conversation.prompt import build_system_prompt
from assistant.core.events import ApprovalRequired, ToolFinished
from assistant.core.skills import store
from assistant.core.tools.approval import UNATTENDED_DENIAL
from tests.conftest import collect


@pytest.fixture
def skills_dir(isolated_settings, monkeypatch):
    monkeypatch.setattr("assistant.core.config.settings.skills_dir", str(isolated_settings / "skills"))
    return isolated_settings / "skills"


async def _approve(service, session, events, approved=True):
    approval = next(e for e in events if isinstance(e, ApprovalRequired))
    return approval, await collect(service.resume(session, {approval.interrupt_id: {"approved": approved}}))


def _outputs(events):
    return [e.output for e in events if isinstance(e, ToolFinished)]


async def test_save_use_list_and_delete_a_skill(service, script, skills_dir):
    script.call("save_skill", name="news-digest", description="Daily news summary", instructions="1. Search\n2. Email")
    script.call("use_skill", name="news-digest").reply("done")
    session = await service.session("u", "cli")
    approval, events = await _approve(service, session, await collect(service.send(session, "make a skill")))
    assert approval.request["tool"] == "save_skill" and "1. Search" in approval.request["command"]
    outputs = _outputs(events)
    assert outputs[0].startswith("Saved skill news-digest") and "2. Email" in outputs[1]
    assert (skills_dir / "news-digest" / "SKILL.md").read_text().startswith("---\n")
    prompt = await build_system_prompt(service.store, "u", "", "")
    assert "- news-digest: Daily news summary" in prompt
    store.delete("news-digest")
    assert [s.name for s in store.list_skills() if not s.builtin] == []


async def test_a_skill_with_files_is_shown_whole_before_approval_and_rejecting_saves_nothing(
    service, script, skills_dir
):
    files = {"scripts/add.py": "print('added')", "references/categories.md": "- food"}
    script.call(
        "save_skill", name="expenses", description="Track expenses", instructions="Run scripts/add.py", files=files
    )
    script.reply("not saved")
    session = await service.session("u", "cli")
    approval, events = await _approve(service, session, await collect(service.send(session, "save")), approved=False)
    assert "--- scripts/add.py ---\nprint('added')" in approval.request["command"]
    assert _outputs(events)[0].startswith("The user rejected this") and not (skills_dir / "expenses").exists()


async def test_use_skill_gives_the_folder_files_and_python(service, script, skills_dir):
    store.save("expenses", "Track expenses", "Run scripts/add.py", {"scripts/add.py": "print(1)"})
    script.call("use_skill", name="expenses").reply("done")
    output = _outputs(await collect(service.send(await service.session("u", "cli"), "add")))[0]
    assert str(skills_dir / "expenses") in output and sys.executable in output and "- scripts/add.py" in output


def test_files_are_kept_unless_replaced(skills_dir):
    store.save("expenses", "d", "i", {"scripts/add.py": "1", "scripts/old.py": "2"})
    assert store.save("expenses", "d2", "i2").files == ["scripts/add.py", "scripts/old.py"]
    assert store.save("expenses", "d", "i", {"scripts/add.py": "3"}).files == ["scripts/add.py"]
    assert (skills_dir / "expenses" / "scripts" / "add.py").read_text() == "3"


@pytest.mark.parametrize("path", ["../escape.py", "/etc/passwd", ".hidden", "scripts/.env", "SKILL.md", "a\\b"])
def test_file_paths_outside_the_folder_hidden_or_reserved_are_refused(skills_dir, path):
    with pytest.raises(store.SkillError, match="valid skill file path"):
        store.save("expenses", "d", "i", {path: "x"})
    assert not (skills_dir / "expenses").exists()


async def test_deleting_a_skill_needs_approval_and_is_denied_unattended(service, script, skills_dir):
    store.save("news-digest", "d", "i")
    script.call("delete_skill", name="news-digest").reply("couldn't")
    events = await collect(service.send(await service.session("u", "worker"), "delete it"))
    assert _outputs(events)[0].startswith(UNATTENDED_DENIAL) and store.load("news-digest")
    script.call("delete_skill", name="news-digest").reply("deleted")
    session = await service.session("u", "cli")
    _, events = await _approve(service, session, await collect(service.send(session, "delete it")))
    assert _outputs(events) == ["Deleted skill news-digest."]


def test_invalid_names_are_refused(isolated_settings, monkeypatch):
    monkeypatch.setattr("assistant.core.config.settings.skills_dir", str(isolated_settings / "skills"))
    import pytest

    with pytest.raises(store.SkillError):
        store.save("Bad Name!", "d", "i")


def test_the_setup_skill_is_built_in_and_covers_every_setup_command(isolated_settings, monkeypatch):
    import pytest

    from assistant_terminal.commands import COMMANDS

    monkeypatch.setattr("assistant.core.config.settings.skills_dir", str(isolated_settings / "skills"))
    setup = store.load(store.SETUP)
    assert setup.builtin and next(s for s in store.list_skills() if s.name == store.SETUP).builtin
    assert "Settings → Plugins" in setup.instructions and "Settings → General → Email" in setup.instructions
    # Every command that sets something up must be explained in it, so it can't fall behind.
    for command in (
        "/model",
        "/audio",
        "/websearch",
        "/email",
        "/mcp",
        "/plugins",
        "/skills",
        "/startup",
        "/name",
        "/devices",
    ):
        assert command in {c.name for c in COMMANDS} and f"`{command}" in setup.instructions
    for change in (lambda: store.save(store.SETUP, "d", "i"), lambda: store.delete(store.SETUP)):
        with pytest.raises(store.SkillError, match="built into"):
            change()


async def test_send_email_points_to_setting_up_email_when_none_is_connected(service, script):
    script.call("send_email", to=["me@example.com"], subject="Hi", body="Hi").reply("ok")
    events = await collect(service.send(await service.session("u", "web"), "email me hi"))
    output = next(e.output for e in events if hasattr(e, "output"))
    assert "Call set_up_email" in output


async def test_saved_skills_are_edited_and_built_in_ones_refused(service, isolated_settings, monkeypatch):
    import pytest

    monkeypatch.setattr("assistant.core.config.settings.skills_dir", str(isolated_settings / "skills"))
    store.save("news-digest", "Daily news", "1. Search")
    edited = await service.update_skill("news-digest", "Morning news", "1. Search\n2. Send")
    assert (edited.description, edited.instructions) == ("Morning news", "1. Search\n2. Send")
    assert store.load("news-digest").description == "Morning news"
    with pytest.raises(store.SkillError, match="built into"):
        await service.update_skill(store.SETUP, "d", "i")
    with pytest.raises(store.SkillError, match="needs a description"):
        await service.update_skill("news-digest", " ", "i")
    with pytest.raises(store.SkillError, match="No skill"):
        await service.update_skill("missing", "d", "i")


async def test_clients_list_only_saved_skills_while_the_assistant_sees_all(service, isolated_settings, monkeypatch):
    monkeypatch.setattr("assistant.core.config.settings.skills_dir", str(isolated_settings / "skills"))
    store.save("news-digest", "Daily news", "1. Search")
    assert [s.name for s in await service.list_skills()] == ["news-digest"]
    assert (await service.memory_snapshot("owner")).skills == ["news-digest"]
    prompt = await build_system_prompt(service.store, "owner", "", "")
    assert f"- {store.SETUP}:" in prompt and "- news-digest:" in prompt
