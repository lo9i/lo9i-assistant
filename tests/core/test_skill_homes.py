"""Messages sent the same way each time for the same skill go to that skill's home conversation, without the model;
one that still lands in a new conversation is merged into the home afterwards. A run that fails tells the chat in one
line, and the inbox's memory leaves out the messages it sent on."""

import io

import httpx
from langchain_core.messages import HumanMessage
from PIL import Image

from lo9i.core import conversations
from lo9i.core.agent import AssistantService, Session
from lo9i.core.attachments import Attachment
from lo9i.core.channels.chat.port import ChatLimits
from lo9i.core.channels.chat.turn import ChatTurn
from lo9i.core.conversation import pending, skill_homes
from lo9i.core.conversation.dispatch import QUICK, Pick
from lo9i.core.conversation.pending import PendingPart
from lo9i.core.conversation.skill_homes import IMAGE, LINK, Kind, kind_of
from lo9i.core.events import Dispatched, Error
from lo9i.core.i18n import texts
from tests.conftest import collect


def _photo() -> Attachment:
    image = io.BytesIO()
    Image.new("RGB", (4, 4)).save(image, "PNG")
    return Attachment("poster.png", "image/png", image.getvalue())


async def _sent_on(service: AssistantService, caption: str, skill: str, script) -> Dispatched:
    """A photo sent on Telegram, routed from the inbox and handled where it went by `skill` ("" for no skill)."""
    inbox = Session("owner", "telegram", await service.inbox_thread("owner"))
    [sent] = [e for e in await collect(service.send(inbox, caption, [_photo()])) if isinstance(e, Dispatched)]
    side = Session("owner", "telegram", sent.thread_id or await service.new_thread("owner"))
    if skill:
        script.call("use_skill", name=skill)
    script.reply("Added.")
    await collect(service.send_dispatched(side, sent.id))
    return sent


def test_a_message_s_kind_is_its_channel_what_it_carries_and_its_caption():
    photo = HumanMessage(
        [
            {"type": "non_standard", "value": {"upload": {"media_type": "image/jpeg"}}},
            {"type": "text", "text": "  Add to  Watchlist "},
        ]
    )
    assert kind_of(photo, "telegram") == Kind("telegram", IMAGE, "add to watchlist")
    assert kind_of(HumanMessage("watchlist https://imdb.com/t/1"), "slack") == Kind("slack", LINK, "watchlist")
    assert Kind("telegram", IMAGE, "watchlist").matches(Kind("telegram", IMAGE, ""))
    assert not Kind("telegram", IMAGE, "watchlist").matches(Kind("telegram", IMAGE, "receipt"))
    assert not Kind("telegram", IMAGE, "").matches(Kind("web", IMAGE, ""))


async def test_three_alike_messages_ending_in_one_skill_send_the_next_to_its_home(dispatch, service, script):
    for caption in ("Watchlist", "", "watchlist"):
        await _sent_on(service, caption, "watchlist", script)
    asked = len(dispatch.inputs)
    sent = await _sent_on(service, "Watchlist", "watchlist", script)
    assert len(dispatch.inputs) == asked  # no model call
    home = await skill_homes.home(service.store, "owner", "watchlist")
    assert home is not None and sent.thread_id == home.thread_id and home.title == "Watchlist"
    assert await conversations.set_title(service.store, "owner", home.thread_id, "Gachiakuta", []) is False
    await service.delete_conversation("owner", home.thread_id)
    again = await _sent_on(service, "", "watchlist", script)
    remade = await skill_homes.home(service.store, "owner", "watchlist")
    assert remade is not None and again.thread_id == remade.thread_id != home.thread_id


async def test_messages_that_ended_in_other_skills_or_none_are_no_habit(dispatch, service, script):
    for skill in ("watchlist", "", "watchlist"):
        await _sent_on(service, "watchlist", skill, script)
    await _sent_on(service, "watchlist", "watchlist", script)
    assert await skill_homes.home(service.store, "owner", "watchlist") is None


async def test_a_new_conversation_that_used_only_a_skill_with_a_home_goes_on_there(dispatch, service, script):
    home = await skill_homes.make_home(service.store, "owner", "watchlist")
    sent = await _sent_on(service, "look at this", "watchlist", script)
    [new] = [c for c in await conversations.recent(service.store, "owner") if c.title == "look at this"]
    assert await service.merge_into_home("owner", new.thread_id, sent.id) == home.thread_id
    assert await conversations.load(service.store, "owner", new.thread_id) is None
    shown = [m.text for m in await service.conversation_messages(home.thread_id)]
    assert shown[0].endswith("look at this") and shown[-1] == "Added."
    inbox_lines = [m.text for m in await service.conversation_messages(await service.inbox_thread("owner"))]
    assert inbox_lines[1:] == ["→ Continued in “Watchlist”."]  # in place of "Started a new conversation"


async def test_a_new_conversation_with_no_skill_or_more_than_one_exchange_stays(dispatch, service, script):
    await skill_homes.make_home(service.store, "owner", "watchlist")
    sent = await _sent_on(service, "plan my week", "", script)
    [new] = [c for c in await conversations.recent(service.store, "owner") if c.title == "plan my week"]
    assert await service.merge_into_home("owner", new.thread_id, sent.id) is None
    assert await conversations.load(service.store, "owner", new.thread_id) is not None


async def test_a_run_that_cant_reach_the_model_says_so_in_short(service, script):
    script.refuse(httpx.ConnectError("unreachable"))
    session = Session("owner", "telegram", await service.new_thread("owner"))
    [error] = [e for e in await collect(service.send(session, "hi")) if isinstance(e, Error)]
    assert error.failed == "connection error"


class _Port:
    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send(self, text: str, **_) -> str:
        self.sent.append(text)
        return str(len(self.sent))

    async def edit(self, *_, **__) -> None: ...
    async def typing(self) -> None: ...
    async def voice(self, ogg_opus: bytes) -> None: ...


async def test_a_chat_is_told_once_when_its_run_failed():
    port = _Port()

    async def events():
        yield Error("APIConnectionError: Connection error.", failed="connection error")

    await ChatTurn(port, ChatLimits(), texts("en")).render(events())
    assert port.sent == ["⚠️ Couldn't finish that (connection error). Send it again."]


async def test_the_inbox_s_memory_leaves_out_the_messages_it_sent_on(dispatch, service, script, digests):
    await _sent_on(service, "Watchlist", "watchlist", script)
    inbox = await service.inbox_thread("owner")
    script.reply("Paris.")
    dispatch.picks.append(Pick(QUICK, 1.0, ""))
    question = "what is the capital of France, and how many people live there these days, roughly?"
    await collect(service.send(Session("owner", "telegram", inbox), question))
    count = len(await service.conversation_messages(inbox))
    await pending.add(service.store, "owner", PendingPart(inbox, 0, count + 5, "", "2026-11-05", "2026-11-05"))
    await service.memory_writer.write_all()
    transcript = digests.inputs[-1].transcript
    assert "France" in transcript and "Watchlist" not in transcript and "conversation" not in transcript
