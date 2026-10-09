"""What a channel's chat does with what the user sends: a message runs and is shown in the chat it came
from, buttons answer what the run waits for, commands move between home and side conversations."""

import asyncio
from collections.abc import AsyncIterator

import pytest

from assistant.core.approvals import RemoteApprovals
from assistant.core.channels.chat.conversations import GREETING, ChannelChats
from assistant.core.channels.chat.port import ChatLimits
from assistant.core.events import Event, TextDelta
from assistant.core.outbox import DeliveryError
from tests.conftest import collect

_INSTANT = ChatLimits(edit_seconds=0)
_SOURCES = ["Google", "GitHub", "X"]


class _Runs:
    """Runs the events as they come; the daemon's runs also show them to every client. The fake model
    doesn't stream, so `say` stands for the text a reply streams."""

    def __init__(self, say: str = "") -> None:
        self.texts: list[str] = []
        self._say = say

    async def follow(self, channel, thread_id, events: AsyncIterator[Event], text: str):
        self.texts.append(text)
        if self._say:
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
        return str(len(self.ops)) if kind == "send" else ""

    def limits(self, channel):
        return self._limits

    def sent(self) -> list[str]:
        return [data["text"] for kind, data in self.ops if kind == "send"]

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


async def test_a_message_runs_in_the_channels_conversation_and_shows_in_its_chat(service, channel, jobs, script):
    script.reply("Hello from lo9i")
    await ChannelChats(service, _Runs(say="Hello"), channel, jobs).message("telegram", "42", "hi", [], voice=False)
    assert channel.sent() == ["Hello …"]  # its draft, then the final version
    assert channel.ops[-1] == ("edit", {"chat": "42", "message": "2", "text": "Hello", "markdown": True, "buttons": []})
    assert all(data["chat"] == "42" for _, data in channel.ops)
    session = await service.session("owner", "telegram")
    assert [m.text for m in await service.conversation_messages(session.thread_id)] == ["hi", "Hello from lo9i"]


async def test_a_question_toggles_its_buttons_and_done_answers_it(chats, channel, script):
    script.call("ask_user", question="Which sources?", options=_SOURCES, multiple=True).reply("Searching both.")
    await chats.message("telegram", "42", "look me up", [], voice=False)
    question = next(data for kind, data in channel.ops if kind == "send" and data["buttons"])
    toggle_x = question["buttons"][2][1]
    await chats.press("telegram", "42", "9", "Which sources?", toggle_x)
    redraw = channel.ops[-1]
    assert redraw[0] == "edit" and [b[0] for b in redraw[1]["buttons"]] == ["☐ Google", "☐ GitHub", "☑ X", "✅ Done"]
    await chats.press("telegram", "42", "9", "Which sources?", redraw[1]["buttons"][-1][1])
    assert channel.sent()[-1] == "Picked: X."
    assert script.requests[-1][-1].content.endswith("The user picked: X.")


async def test_an_answered_question_is_said_to_be_gone(chats, channel):
    await chats.press("telegram", "42", "9", "Which sources?", "qp:nope:0")
    assert channel.ops[0] == (
        "edit",
        {"chat": "42", "message": "9", "text": "Which sources?", "markdown": False, "buttons": []},
    )
    assert channel.sent() == ["This question isn't waiting for an answer any more."]


async def test_moving_to_a_side_conversation_sends_the_brief_there(chats, runs, channel, script, service):
    script.call("suggest_side_conversation", title="Taxes", brief="Do the 2026 return.").reply("Moved.")
    script.reply("On the return now.")
    home = (await service.session("owner", "telegram")).thread_id
    await chats.message("telegram", "42", "let's do my taxes", [], voice=False)
    move = channel.buttons()[-1][0][1]
    await chats.press("telegram", "42", "5", "Move?", move)
    assert channel.sent()[-1] == "Moved to a side conversation. /home goes back."
    assert runs.texts[-1] == "Carried over from home: Taxes\n\nDo the 2026 return."
    assert (await service.session("owner", "telegram")).thread_id != home


async def test_continuing_a_side_conversation_moves_the_channel_back_to_it(chats, runs, channel, script, service):
    script.reply("Started.")
    side = await service.new_channel_thread("owner", "telegram")
    await collect(service.send(await service.session("owner", "telegram"), "my taxes"))
    await service.channel_home("owner", "telegram")
    script.call("suggest_side_conversation", title="Taxes", brief="Go on.", continue_in=side).reply("Moved.")
    await chats.message("telegram", "42", "back to my taxes", [], voice=False)
    assert channel.sent()[-1].startswith("Continue in your side conversation?")
    await chats.press("telegram", "42", "5", "Continue?", channel.buttons()[-1][0][1])
    assert (await service.session("owner", "telegram")).thread_id == side
    assert runs.texts[-1] == "Carried over from home: Taxes\n\nGo on."


async def test_a_job_request_is_answered_from_its_buttons(chats, channel, jobs):
    await chats.press("slack", "D1", "7", "The job is waiting", "ja:i1")
    assert channel.sent() == ["This request isn't waiting any more: the job's run already went on without it."]
    jobs._waiting["i2"] = asyncio.get_running_loop().create_future()
    await chats.press("slack", "D1", "7", "The job is waiting", "jr:i2")
    assert jobs._waiting["i2"].result() == {"approved": False, "reason": "rejected in Slack"}
    assert channel.sent()[-1] == "Rejected. The job goes on without it."


async def test_commands_move_between_home_and_a_side_conversation(chats, service):
    home = (await service.session("owner", "telegram")).thread_id
    assert await chats.command("telegram", "new") == "Started a side conversation. /home goes back."
    assert (await service.session("owner", "telegram")).thread_id != home
    assert await chats.command("telegram", "home") == "Back home."
    assert (await service.session("owner", "telegram")).thread_id == home
    assert await chats.command("telegram", "start") == GREETING
    assert await chats.command("telegram", "pin") == "Unknown command /pin."


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
    session = await service.session("owner", "telegram")
    assert [m.text for m in await service.conversation_messages(session.thread_id)] == ["hi", "Still here."]


async def test_an_agents_command_hands_the_channels_conversation_to_it_and_back(chats, service, tmp_path):
    from tests.core.test_handoffs import agent_plugin

    assert [c["command"] for c in await service.channel_commands()] == ["new", "home"]
    await service.add_mcp_server(agent_plugin())
    assert (await service.channel_commands())[-1]["command"] == "claude"
    thread = (await service.session("owner", "telegram")).thread_id
    asked = await chats.command("telegram", "claude", "")
    assert asked.startswith("Give Claude Code a folder to work in") and "/claude " in asked
    handed = await chats.command("telegram", "claude", f" {tmp_path} ")
    assert handed.startswith(f"Claude Code answers from your next message, working in {tmp_path}.")
    assert (await service.conversation_agent("owner", thread)).folder == str(tmp_path)
    assert "isn't an existing folder" in await chats.command("telegram", "claude", str(tmp_path / "missing"))
    assert await chats.command("telegram", "claude", "off") == "The assistant answers again from your next message."
    assert await service.conversation_agent("owner", thread) is None
