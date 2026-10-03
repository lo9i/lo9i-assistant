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
    assert "Settings → Integrations → Email" in setup.instructions
    # Every command that sets something up must be explained in it, so it can't fall behind.
    for command in ("/email", "/telegram", "/slack", "/mcp", "/startup", "/name", "/devices"):
        assert command in {c.name for c in COMMANDS} and f"`{command}" in setup.instructions
    for change in (lambda: store.save(store.SETUP, "d", "i"), lambda: store.delete(store.SETUP)):
        with pytest.raises(store.SkillError, match="built into"):
            change()


async def test_send_email_points_to_the_setup_skill_when_email_isnt_set_up(service, script):
    script.call("send_email", to=["me@example.com"], subject="Hi", body="Hi").reply("ok")
    events = await collect(service.send(await service.session("u", "web"), "email me hi"))
    output = next(e.output for e in events if hasattr(e, "output"))
    assert f"Load the {store.SETUP} skill" in output
