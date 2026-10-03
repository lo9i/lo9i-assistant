from assistant.core.conversation.prompt import build_system_prompt
from assistant.core.skills import store
from tests.conftest import collect


async def test_save_use_list_and_delete_a_skill(service, script, isolated_settings, monkeypatch):
    monkeypatch.setattr("assistant.core.config.settings.skills_dir", str(isolated_settings / "skills"))
    script.call("save_skill", name="news-digest", description="Daily news summary", instructions="1. Search\n2. Email")
    script.call("use_skill", name="news-digest").reply("done")
    events = await collect(service.send(await service.session("u", "cli"), "make a skill"))
    outputs = [e.output for e in events if hasattr(e, "output")]
    assert outputs[0].startswith("Saved skill news-digest") and "2. Email" in outputs[1]
    assert (isolated_settings / "skills" / "news-digest" / "SKILL.md").read_text().startswith("---\n")
    prompt = await build_system_prompt(service.store, "u", "", "")
    assert "- news-digest: Daily news summary" in prompt
    store.delete("news-digest")
    assert [s.name for s in store.list_skills()] == [store.SETUP]


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
    assert "Settings → Integrations → Email" in setup.instructions
    # Every command that sets something up must be explained in it, so it can't fall behind.
    for command in ("/model", "/audio", "/email", "/telegram", "/slack", "/mcp", "/startup", "/name", "/devices"):
        assert command in {c.name for c in COMMANDS} and f"`{command}" in setup.instructions
    for change in (lambda: store.save(store.SETUP, "d", "i"), lambda: store.delete(store.SETUP)):
        with pytest.raises(store.SkillError, match="built into"):
            change()


async def test_send_email_points_to_the_setup_skill_when_email_isnt_set_up(service, script):
    script.call("send_email", to=["me@example.com"], subject="Hi", body="Hi").reply("ok")
    events = await collect(service.send(await service.session("u", "web"), "email me hi"))
    output = next(e.output for e in events if hasattr(e, "output"))
    assert f"Load the {store.SETUP} skill" in output


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
