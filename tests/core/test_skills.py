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
    assert store.list_skills() == []


def test_invalid_names_are_refused(isolated_settings, monkeypatch):
    monkeypatch.setattr("assistant.core.config.settings.skills_dir", str(isolated_settings / "skills"))
    import pytest

    with pytest.raises(store.SkillError):
        store.save("Bad Name!", "d", "i")
