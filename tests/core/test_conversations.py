"""The conversation list: recording, showing, leaving, and archiving each part only once."""

import asyncio

import pytest

from assistant.core import conversations
from assistant.core.agent import ConversationError, Session
from assistant.core.context import UNATTENDED_CHANNEL
from tests.conftest import collect


async def _say(service, text, session=None):
    await collect(service.send(session or await service.session("owner", "cli"), text))


async def _archived(service):
    await asyncio.gather(*service._background)


async def test_messages_are_listed_titled_by_the_first_one_until_the_model_titles_them(service, script, titles):
    titles.error = RuntimeError("model down")
    await _say(service, "plan my   trip to Rome")
    await _say(service, "and book a hotel")
    await collect(service.send(Session("owner", UNATTENDED_CHANNEL, "job:news:1"), "run the job"))
    await _archived(service)
    [listed] = await service.list_conversations("owner")
    assert listed.title == "plan my trip to Rome" and not listed.titled
    assert listed.updated_at > listed.started_at
    titles.error = None
    assert await service.title_untitled("owner") == 1
    assert [c.title for c in await service.list_conversations("owner")] == ["Trip to Rome"]
    assert await service.title_untitled("owner") == 0


async def test_a_conversation_records_the_channels_it_was_used_from(service):
    cli = await service.session("owner", "cli")
    await _say(service, "one", cli)
    await _say(service, "two", Session("owner", "web", cli.thread_id))
    await _say(service, "three", cli)
    [listed] = await service.list_conversations("owner")
    assert listed.channels == ["cli", "web"]


async def test_channels_missing_from_older_conversations_are_read_from_their_messages(service):
    cli = await service.session("owner", "cli")
    await _say(service, "one", cli)
    await _say(service, "two", Session("owner", "telegram", cli.thread_id))
    [listed] = await service.list_conversations("owner")
    listed.channels = []
    await conversations.save(service.store, "owner", listed)  # as saved before channels were recorded
    assert await service.fill_channels("owner") == 1
    assert (await service.list_conversations("owner"))[0].channels == ["cli", "telegram"]
    assert await service.fill_channels("owner") == 0


async def test_the_model_titles_after_the_first_and_third_reply_and_when_left(service, script, titles):
    for text in ("plan my trip to Rome", "and book a hotel", "near the Colosseum", "thanks"):
        await _say(service, text)
        await _archived(service)
    assert len(titles.inputs) == 2
    assert titles.inputs[0] == "User: plan my trip to Rome\n\nAssistant: ok"  # no turn headers
    [listed] = await service.list_conversations("owner")
    assert listed.title == "Trip to Rome" and listed.titled
    await service.new_channel_thread("owner", "cli")
    await _archived(service)
    assert len(titles.inputs) == 3 and "thanks" in titles.inputs[2]


async def test_shown_messages_leave_out_turn_headers_and_tool_output(service, script):
    script.call("remember", fact="likes Rome").reply("Saved!")
    await _say(service, "remember I like Rome")
    session = await service.session("owner", "cli")
    shown = await service.conversation_messages(session.thread_id)
    assert [(m.role, m.text) for m in shown] == [
        ("user", "remember I like Rome"),
        ("tool", "remember"),
        ("assistant", "Saved!"),
    ]


async def test_leaving_a_conversation_again_archives_only_what_is_new(service, script, digests):
    session = await service.session("owner", "cli")
    await _say(service, "one")
    await _say(service, "two")
    service.leave_thread("owner", session.thread_id)
    await _archived(service)
    await service.require_conversation("owner", session.thread_id)
    await _say(service, "three")
    await _say(service, "four")
    service.leave_thread("owner", session.thread_id)
    await _archived(service)
    transcripts = [d.transcript for d in digests.inputs]
    assert len(transcripts) == 2
    assert "three" in transcripts[1] and "one" not in transcripts[1]
    with pytest.raises(ConversationError):
        await service.require_conversation("owner", "owner:nope")


async def test_conversations_saved_before_the_list_are_indexed(service, script):
    await _say(service, "an old conversation")
    await _archived(service)  # the title written in the background, before the record is removed
    thread_id = (await service.session("owner", "cli")).thread_id
    await service.store.adelete(conversations.namespace("owner"), thread_id)
    assert await service.index_conversations("owner") == 1
    [indexed] = await service.list_conversations("owner")
    assert indexed.title == "an old conversation" and indexed.channels == ["cli"]
    assert await service.index_conversations("owner") == 0


def test_a_model_reply_becomes_a_clean_title():
    from assistant.core.conversation.titles import _clean

    assert _clean('\n"Trip to Rome."\nBecause the user…') == "Trip to Rome"
    assert _clean("**Hotel  booking**") == "Hotel booking"


async def test_deleting_removes_the_messages_the_listing_and_the_files(service, script, isolated_settings):
    from assistant.core.attachments import Attachment
    from tests.core.test_speech import FakeTranscriber

    service._transcriber = FakeTranscriber()
    session = await service.session("owner", "telegram")
    note = Attachment("notes.txt", "text/plain", b"buy milk")
    voice = Attachment("voice.ogg", "audio/ogg", b"fake audio")
    await collect(service.send(session, "read this", [note]))
    await collect(service.send(session, "", [voice]))
    uploads = isolated_settings / "uploads"
    assert len([p for p in uploads.rglob("*") if p.is_file()]) == 2
    await service.delete_conversation("owner", session.thread_id)
    assert await service.list_conversations("owner") == []
    assert await service.conversation_messages(session.thread_id) == []
    assert [p for p in uploads.rglob("*") if p.is_file()] == []
    assert (await service.session("owner", "telegram")).thread_id != session.thread_id  # Telegram starts anew


async def test_deleting_an_unknown_or_busy_conversation_is_refused(service):
    from assistant.core.agent import ConversationBusyError

    with pytest.raises(ConversationError, match="No conversation"):
        await service.delete_conversation("owner", "owner:nope")
    session = await service.session("owner", "cli")
    await _say(service, "hi", session)
    service._active_runs[session.thread_id] = asyncio.get_running_loop().create_future()
    with pytest.raises(ConversationBusyError):
        await service.delete_conversation("owner", session.thread_id)
