"""What a channel's chat does with what the user sends: a new message goes to the inbox, which routes it,
a reply goes on in its message's conversation, /new starts a new one; each run is shown in the chat it came
from with its conversation's tag, and buttons answer what their message's run waits for."""

import asyncio
from collections.abc import AsyncIterator

import pytest

from assistant.core.agent import Session
from assistant.core.approvals import RemoteApprovals
from assistant.core.channels.chat.conversations import GREETING, ChannelChats
from assistant.core.channels.chat.port import ChatLimits, Delivered
from assistant.core.conversation.dispatch import Pick
from assistant.core.events import Event, TextDelta
from assistant.core.outbox import DeliveryError
from tests.conftest import collect
from tests.core.test_handoffs import agent_plugin

_INSTANT = ChatLimits(edit_seconds=0)
_SOURCES = ["Google", "GitHub", "X"]


class _Runs:
    """Runs the events as they come; the daemon's runs also show them to every client. The fake model
    doesn't stream, so `say` stands for the text a reply streams."""

    def __init__(self, say: str = "", quiet_in: str = "") -> None:
        self.texts: list[str] = []
        self.briefs: list[str] = []
        self._say = say
        # A conversation whose runs say nothing: the inbox, which sends a message on without a reply.
        self._quiet_in = quiet_in

    async def follow(self, channel, thread_id, events: AsyncIterator[Event], text: str, brief: str = ""):
        self.texts.append(text)
        self.briefs.append(brief)
        if self._say and thread_id != self._quiet_in:
            yield TextDelta(self._say)
        async for event in events:
            yield event


class _Channel:
    """The channel's process: records each operation and answers with a message id."""

    def __init__(self, limits: ChatLimits = _INSTANT) -> None:
        self.ops: list[tuple[str, dict]] = []
        self._limits = limits
        self.refuse = False

    async def operate(self, channel, kind, data):
        if self.refuse:
            raise DeliveryError("telegram isn't connected.")
        self.ops.append((kind, data))
        return Delivered(str(len(self.ops)) if kind == "send" else "")

    def limits(self, channel):
        return self._limits

    def sent(self) -> list[str]:
        return [data["text"] for kind, data in self.ops if kind == "send"]

    def last_sent(self) -> str:
        """The id the last message sent was given."""
        return str(max(i for i, (kind, _) in enumerate(self.ops, 1) if kind == "send"))

    def shown(self) -> list[str]:
        """The messages' texts as the chat shows them, edits included."""
        texts: dict[str, str] = {}
        for i, (kind, data) in enumerate(self.ops, 1):
            if kind in ("send", "edit"):
                texts[data.get("message", str(i)) if kind == "edit" else str(i)] = data["text"]
        return list(texts.values())

    def buttons(self) -> list[list[list[str]]]:
        return [data["buttons"] for kind, data in self.ops if kind == "send" and data["buttons"]]


@pytest.fixture
def channel() -> _Channel:
    return _Channel()


@pytest.fixture
def jobs() -> RemoteApprovals:
    return RemoteApprovals()


@pytest.fixture
def runs() -> _Runs:
    return _Runs()


@pytest.fixture
def chats(service, runs, channel, jobs) -> ChannelChats:
    return ChannelChats(service, runs, channel, jobs)


async def test_a_message_runs_in_the_inbox_and_shows_in_its_chat(service, channel, jobs, script):
    script.reply("Hello from lo9i")
    await ChannelChats(service, _Runs(say="Hello"), channel, jobs).message("telegram", "42", "hi", [], voice=False)
    assert channel.sent() == ["[inbox] Hello …"]  # its draft, then the final version
    assert channel.ops[-1] == (
        "edit",
        {"chat": "42", "message": channel.last_sent(), "text": "[inbox] Hello", "markdown": True, "buttons": []},
    )
    assert all(data["chat"] == "42" for _, data in channel.ops)
    inbox = await service.inbox_thread("owner")
    assert [m.text for m in await service.conversation_messages(inbox)] == ["hi", "Hello from lo9i"]


async def test_a_question_toggles_its_buttons_and_done_answers_it(chats, channel, script):
    script.call("ask_user", question="Which sources?", options=_SOURCES, multiple=True).reply("Searching both.")
    await chats.message("telegram", "42", "look me up", [], voice=False)
    question = next((i, data) for i, (kind, data) in enumerate(channel.ops, 1) if kind == "send" and data["buttons"])
    on, data = str(question[0]), question[1]
    toggle_x = data["buttons"][2][1]
    await chats.press("telegram", "42", on, "Which sources?", toggle_x)
    redraw = channel.ops[-1]
    assert redraw[0] == "edit" and [b[0] for b in redraw[1]["buttons"]] == ["☐ Google", "☐ GitHub", "☑ X", "✅ Done"]
    await chats.press("telegram", "42", on, "Which sources?", redraw[1]["buttons"][-1][1])
    assert channel.sent()[-1] == "Picked: X."
    assert script.requests[-1][-1].content.endswith("The user picked: X.")


async def test_an_answered_question_is_said_to_be_gone(chats, channel):
    await chats.press("telegram", "42", "9", "Which sources?", "qp:nope:0")
    assert channel.ops[0] == (
        "edit",
        {"chat": "42", "message": "9", "text": "Which sources?", "markdown": False, "buttons": []},
    )
    assert channel.sent() == ["This question isn't waiting for an answer any more."]


async def test_the_inbox_sends_a_message_on_and_the_reply_is_tagged_with_where(
    dispatch, service, runs, channel, jobs, script, titles
):
    taxes = await service.new_thread("owner")
    titles.title, titles.tags = "The 2026 tax return", ["taxes"]
    script.reply("Started.")
    await collect(service.send(Session("owner", "web", taxes), "my taxes"))
    await asyncio.gather(*service._background)
    dispatch.picks.append(Pick(taxes, 0.9, ""))
    script.reply("On the taxes.")
    runs = _Runs(say="On the taxes.", quiet_in=await service.inbox_thread("owner"))
    await ChannelChats(service, runs, channel, jobs).message("telegram", "42", "what about my taxes?", [], voice=False)
    assert channel.shown() == ["[taxes] On the taxes."]
    assert runs.texts[-1] == "what about my taxes?"
    shown = [m.text for m in await service.conversation_messages(taxes)]
    assert shown == ["my taxes", "Started.", "what about my taxes?", "On the taxes."]
    assert await service.channel_thread("owner", "telegram") == taxes


async def test_a_new_conversation_is_tagged_with_its_first_words(dispatch, channel, jobs, script, service):
    script.reply("Here's a plan.")
    runs = _Runs(say="Here's a plan.", quiet_in=await service.inbox_thread("owner"))
    await ChannelChats(service, runs, channel, jobs).message("telegram", "42", "plan my week please", [], voice=False)
    assert channel.shown() == ["[plan my week] Here's a plan."]
    assert await service.channel_thread("owner", "telegram") != await service.inbox_thread("owner")


async def test_replying_to_a_message_goes_on_in_its_conversation(dispatch, channel, jobs, script, service):
    chats = ChannelChats(service, _Runs(say="Sure.", quiet_in=await service.inbox_thread("owner")), channel, jobs)
    script.reply("Here's a plan.")
    await chats.message("telegram", "42", "plan my week", [], voice=False, message="m1")
    planned = await service.channel_thread("owner", "telegram")
    reply = channel.last_sent()
    script.reply("Moved it.")
    await chats.message("telegram", "42", "move gym to friday", [], voice=False, reply_to=reply)
    assert len(dispatch.inputs) == 1  # the reply wasn't routed
    shown = [m.text for m in await service.conversation_messages(planned)]
    assert shown == ["plan my week", "Here's a plan.", "move gym to friday", "Moved it."]
    script.reply("And Saturday too.")
    await chats.message("telegram", "42", "and saturday?", [], voice=False, reply_to="m1")
    assert [m.text for m in await service.conversation_messages(planned)][-1] == "And Saturday too."


async def test_new_sends_the_next_message_to_a_new_conversation(dispatch, chats, channel, script, service):
    assert await chats.command("telegram", "new") == "Your next message starts a new conversation."
    script.reply("Hi.")
    await chats.message("telegram", "42", "a fresh start", [], voice=False)
    assert dispatch.inputs == []
    fresh = await service.channel_thread("owner", "telegram")
    assert [m.text for m in await service.conversation_messages(fresh)] == ["a fresh start", "Hi."]
    script.reply("Routed.")
    await chats.message("telegram", "42", "something else", [], voice=False)
    assert len(dispatch.inputs) == 1
    assert await chats.command("telegram", "start") == GREETING
    assert await chats.command("telegram", "pin") == "Unknown command /pin."
    await service.set_language("es")
    assert await chats.command("telegram", "new") == "Tu próximo mensaje empieza una conversación nueva."


async def test_a_coding_task_moves_to_a_new_conversation_handed_to_its_agent(
    chats, runs, channel, script, service, tmp_path
):
    await service.add_mcp_server(agent_plugin(trusted=True))
    script.call("start_task", agent="claude-code", repository=str(tmp_path), task="finish").reply("Moved.")
    await chats.message("telegram", "42", "fix the tests with claude", [], voice=False)
    moved = await service.channel_thread("owner", "telegram")
    handoff = await service.conversation_agent("owner", moved)
    assert handoff is not None and handoff.folder == str(tmp_path)
    assert runs.texts[-1] == "finish"


async def test_a_job_request_is_answered_from_its_buttons(chats, channel, jobs):
    await chats.press("slack", "D1", "7", "The job is waiting", "ja:i1")
    assert channel.sent() == ["This request isn't waiting any more: the job's run already went on without it."]
    jobs._waiting["i2"] = asyncio.get_running_loop().create_future()
    await chats.press("slack", "D1", "7", "The job is waiting", "jr:i2")
    assert jobs._waiting["i2"].result() == {"approved": False, "reason": "rejected in Slack"}
    assert channel.sent()[-1] == "Rejected. The job goes on without it."


async def test_a_reply_is_spoken_only_where_voice_notes_can_be_sent(service, script, jobs, monkeypatch):
    async def speaks(after_voice_message):
        return True

    async def speak(text, audio_format="wav", voice=""):
        return b"OggS" + text.encode()

    monkeypatch.setattr(service, "speaks_reply", speaks)
    monkeypatch.setattr(service, "speak", speak)
    telegram, slack = _Channel(ChatLimits(edit_seconds=0, voice=True)), _Channel()
    for channel in (telegram, slack):
        script.reply("Done.")
        await ChannelChats(service, _Runs(say="Done."), channel, jobs).message("x", "1", "go", [], voice=True)
    assert ("voice", {"chat": "1", "audio": "T2dnU0RvbmUu"}) in telegram.ops
    assert all(kind != "voice" for kind, _ in slack.ops)


async def test_a_channel_that_went_away_stops_the_turn_and_the_run_goes_on(chats, channel, script, service):
    script.reply("Still here.")
    channel.refuse = True
    chats.spawn(chats.message("telegram", "42", "hi", [], voice=False))
    for _ in range(100):
        if not chats._tasks:
            break
        await asyncio.sleep(0.01)
    inbox = await service.inbox_thread("owner")
    assert [m.text for m in await service.conversation_messages(inbox)] == ["hi", "Still here."]


async def test_an_agents_command_hands_the_channels_conversation_to_it_and_back(chats, service, script, tmp_path):
    assert [c["command"] for c in await service.channel_commands()] == ["new"]
    await service.add_mcp_server(agent_plugin())
    assert (await service.channel_commands())[-1]["command"] == "claude"
    asked = await chats.command("telegram", "claude", "")
    assert asked.startswith("Give Claude Code a folder to work in") and "/claude " in asked
    handed = await chats.command("telegram", "claude", f" {tmp_path} ")
    assert handed.startswith(f"Claude Code answers from your next message, working in {tmp_path}.")
    thread = await service.channel_thread("owner", "telegram")
    assert thread != await service.inbox_thread("owner")  # the inbox isn't handed: a new conversation is
    assert (await service.conversation_agent("owner", thread)).folder == str(tmp_path)
    assert "isn't an existing folder" in await chats.command("telegram", "claude", str(tmp_path / "missing"))
    assert await chats.command("telegram", "claude", "off") == "The assistant answers again from your next message."
    assert await service.conversation_agent("owner", thread) is None
