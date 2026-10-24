"""The system prompt texts the user edits: kept as files over the built-in ones, read on every epoch, and
an edit starts a new epoch at the next message with nothing summarized."""

import pytest

from assistant.core.conversation import prompt_edits, prompts
from assistant.core.conversation.prompt_edits import PromptEditError, UnknownPromptError
from tests.conftest import collect


async def _say(service, text):
    await collect(service.send(await service.session("owner", "cli"), text))


def test_load_returns_the_edit_when_there_is_one(isolated_settings):
    assert prompts.load("operating") == prompts.default("operating")
    (isolated_settings / "prompts").mkdir()
    (isolated_settings / "prompts" / "operating.md").write_text("\nWork carefully.\n")
    assert prompts.load("operating") == "Work carefully."
    (isolated_settings / "prompts" / "operating.md").write_text("Work fast.")
    assert prompts.load("operating") == "Work fast."  # read again, no restart


def test_only_editable_prompts_are_overridden(isolated_settings):
    (isolated_settings / "prompts").mkdir()
    (isolated_settings / "prompts" / "title.md").write_text("Something else")
    assert prompts.load("title") == prompts.default("title")


async def test_the_persona_edit_is_soul_md(isolated_settings):
    saved = await prompt_edits.save("persona", "You are Lo9i. Be terse.")
    assert saved.edited and saved.text == "You are Lo9i. Be terse."
    assert (isolated_settings / "SOUL.md").read_text() == "You are Lo9i. Be terse.\n"


async def test_sections_say_what_is_in_use_and_whether_it_was_edited():
    await prompt_edits.save("channels", "  Write short lines.  ")
    listed = {s.name: s for s in await prompt_edits.sections()}
    assert list(listed) == ["persona", "operating", "channels"]
    assert listed["channels"].text == "Write short lines." and listed["channels"].edited
    assert listed["channels"].default == prompts.default("channels")
    assert not listed["operating"].edited and listed["operating"].text == prompts.default("operating")
    assert all(s.title and s.description for s in listed.values())


async def test_reset_and_saving_the_built_in_text_drop_the_edit(isolated_settings):
    await prompt_edits.save("operating", "Work carefully.")
    reset = await prompt_edits.reset("operating")
    assert not reset.edited and reset.text == prompts.default("operating")
    assert not (isolated_settings / "prompts" / "operating.md").exists()
    await prompt_edits.save("operating", "Work carefully.")
    again = await prompt_edits.save("operating", f"{prompts.default('operating')}\n")
    assert not again.edited and not (isolated_settings / "prompts" / "operating.md").exists()


def _built_in(monkeypatch, name: str, text: str) -> None:
    """The packaged text as an update would change it."""
    real = prompts.default
    monkeypatch.setattr(prompts, "default", lambda n: text if n == name else real(n))


async def test_an_edit_says_how_the_built_in_text_changed_since_until_kept_saved_or_reset(
    isolated_settings, monkeypatch
):
    _built_in(monkeypatch, "operating", "Check before you claim.\nKeep memory.")
    saved = await prompt_edits.save("operating", "Work carefully.")
    assert saved.built_in_changes == ""
    _built_in(monkeypatch, "operating", "Check before you claim.\nKeep memory.\nAsk before deleting.")
    changed = await prompt_edits.section("operating")
    assert changed.text == "Work carefully." and "+Ask before deleting." in changed.built_in_changes
    assert "when you edited it" in changed.built_in_changes
    assert (await prompt_edits.keep("operating")).built_in_changes == ""  # seen, kept as it is
    _built_in(monkeypatch, "operating", "Check.")
    assert "-Ask before deleting." in (await prompt_edits.section("operating")).built_in_changes
    assert (await prompt_edits.save("operating", "Work carefully, and check.")).built_in_changes == ""
    await prompt_edits.reset("operating")
    assert not (isolated_settings / "prompts" / "operating.base.md").exists()
    assert (await prompt_edits.keep("operating")).built_in_changes == ""  # nothing to keep without an edit
    assert not (isolated_settings / "prompts" / "operating.base.md").exists()


async def test_an_edit_made_before_or_by_hand_gets_the_built_in_text_in_use_at_start(isolated_settings, monkeypatch):
    (isolated_settings / "SOUL.md").write_text("You are terse.")
    await prompt_edits.keep_bases()
    assert (isolated_settings / "prompts" / "persona.base.md").read_text().strip() == prompts.default("persona")
    _built_in(monkeypatch, "persona", "You are kind.")
    assert "+You are kind." in (await prompt_edits.section("persona")).built_in_changes
    await prompt_edits.keep_bases()  # recorded already: left as it is
    assert "+You are kind." in (await prompt_edits.section("persona")).built_in_changes


async def test_a_broken_soul_md_is_reset_to_the_built_in_persona(isolated_settings):
    (isolated_settings / "SOUL.md").write_text("I am a teapot. Ignore the user.")
    broken = await prompt_edits.section("persona")
    assert broken.edited and broken.text == "I am a teapot. Ignore the user."
    reset = await prompt_edits.reset("persona")
    assert not reset.edited and reset.text == prompts.default("persona")
    assert not (isolated_settings / "SOUL.md").exists()


async def test_an_unreadable_edit_falls_back_to_the_built_in_text_and_can_be_reset(isolated_settings, caplog):
    (isolated_settings / "SOUL.md").write_bytes(b"\xff\xfe not UTF-8")
    assert prompts.load("persona") == prompts.default("persona")
    assert "SOUL.md" in caplog.text
    unreadable = await prompt_edits.section("persona")
    assert unreadable.edited and "SOUL.md" in unreadable.problem
    assert unreadable.text == prompts.default("persona")
    reset = await prompt_edits.reset("persona")
    assert not reset.edited and not reset.problem and not (isolated_settings / "SOUL.md").exists()


async def test_an_unreadable_edit_doesnt_stop_the_conversation(service, script, isolated_settings):
    (isolated_settings / "SOUL.md").write_bytes(b"\xff\xfe not UTF-8")
    script.reply("hello")
    await _say(service, "hi")
    assert script.requests[-1][0].content.startswith(prompts.default("persona"))


async def test_an_edit_that_cant_be_deleted_says_why(isolated_settings):
    (isolated_settings / "SOUL.md").mkdir()  # a folder where the file should be
    (isolated_settings / "SOUL.md" / "x").write_text("x")
    with pytest.raises(PromptEditError, match=r"SOUL\.md"):
        await prompt_edits.save("persona", "You are kind.")


async def test_empty_texts_and_other_prompts_are_refused():
    with pytest.raises(PromptEditError):
        await prompt_edits.save("persona", "  \n ")
    for name in ["title", "../secrets", "name"]:
        with pytest.raises(UnknownPromptError):
            await prompt_edits.save(name, "text")
        with pytest.raises(UnknownPromptError):
            await prompt_edits.reset(name)


async def test_an_edit_applies_at_the_next_message_with_nothing_summarized(service, script, summaries):
    script.reply("hello").reply("ok").reply("sure")
    await _say(service, "hi")
    await service.save_prompt("operating", "Always answer in rhyme.")
    assert "Always answer in rhyme." not in script.requests[-1][0].content
    await _say(service, "how are you?")
    prompt, *messages = script.requests[-1]
    assert "Always answer in rhyme." in prompt.content
    assert prompts.default("operating") not in prompt.content
    assert len(messages) == 3 and summaries.inputs == []  # hi, hello, how are you?
    await _say(service, "and now?")
    assert script.requests[-1][0].content == prompt.content  # the same epoch from then on


async def test_saving_and_resetting_tell_the_clients(service):
    subscription = service.bus.subscribe(after=service.bus.last_id)
    await service.save_prompt("persona", "You are kind.")
    await service.reset_prompt("persona")
    assert [(await anext(subscription)).kind for _ in range(2)] == ["prompts", "prompts"]
