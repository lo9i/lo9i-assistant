"""Runs kept while an update installed run once the daemon is back, in the order they came, each shown where it came
from: announced to every app with the id their Held event gave, a message the inbox sends on sent on from here, and
a channel's chat or a job's run left to whoever shows it there."""

import asyncio

from assistant.core.agent import Session
from assistant.core.conversation import held
from assistant.core.conversation.held import HeldRun, Origin
from assistant.core.events import Dispatched
from assistant.daemon.held import HeldRuns
from assistant.daemon.runs import RunHub
from assistant.protocol import event_from_dict
from tests.conftest import collect


class _Chats:
    def __init__(self) -> None:
        self.replayed: list[str] = []

    async def replay(self, run: HeldRun) -> None:
        self.replayed.append(run.text)


async def _announced(service, after: int, count: int) -> list[dict]:
    runs = []
    async with asyncio.timeout(10):
        async for event in service.bus.subscribe(after):
            if event.kind == "run":
                runs.append(event.data)
            if event.kind == "run_finished" and len(runs) == count:
                return runs
    raise AssertionError("the bus stopped")


async def _kept(service, session: Session, text: str) -> str:
    [kept] = await collect(service.send(session, text))
    return kept.id


async def test_kept_runs_run_at_start_in_the_order_they_came_announced_with_their_ids(service, script, dispatch):
    later = Session("owner", "web", await service.new_thread("owner"))
    earlier = Session("owner", "web", await service.new_thread("owner"))
    await service.hold_runs()
    first = await _kept(service, later, "first")
    second = await _kept(service, earlier, "second")
    service.release_runs()  # As the daemon starts again on the update, before the replay follows the bus.
    script.reply("One.").reply("Two.")
    after, stop = service.bus.last_id, asyncio.Event()
    replaying = asyncio.create_task(HeldRuns(service, RunHub(service.bus), {}).run(stop))
    runs = await _announced(service, after, 2)
    shown = [(r["thread_id"], r["text"], r["held"], r["client_id"]) for r in runs]
    assert shown == [(later.thread_id, "first", first, ""), (earlier.thread_id, "second", second, "")]
    assert await service.held_runs("owner") == []
    stop.set()
    await replaying


async def test_a_message_the_inbox_sends_on_is_sent_on_and_answered_there(service, script, dispatch):
    inbox = Session("owner", "terminal", await service.inbox_thread("owner"))
    await service.hold_runs()
    await _kept(service, inbox, "plan my week")
    script.reply("Here's a plan.")
    after, stop = service.bus.last_id, asyncio.Event()
    replaying = asyncio.create_task(HeldRuns(service, RunHub(service.bus), {}).run(stop))
    service.release_runs()  # The update failed: the kept runs run at once.
    inbox_run, sent_on = await _announced(service, after, 2)
    assert inbox_run["thread_id"] == inbox.thread_id and sent_on["thread_id"] != inbox.thread_id
    assert (sent_on["text"], sent_on["channel"]) == ("plan my week", "terminal")
    shown = [(m.role, m.text) for m in await service.conversation_messages(sent_on["thread_id"])]
    assert shown == [("user", "plan my week"), ("assistant", "Here's a plan.")]
    stop.set()
    await replaying


async def test_the_client_that_wrote_in_the_inbox_is_told_where_its_message_went(service, script, dispatch):
    inbox = Session("owner", "web", await service.inbox_thread("owner"), held.from_app("tab-1"))
    await service.hold_runs()
    await _kept(service, inbox, "plan my week")
    script.reply("Here's a plan.")
    after, stop = service.bus.last_id, asyncio.Event()
    replaying = asyncio.create_task(HeldRuns(service, RunHub(service.bus), {}).run(stop))
    service.release_runs()
    inbox_run, sent_run = await _announced(service, after, 2)
    # The inbox's run shows in every app; the one where the message went is the client's own, as if it sent it.
    assert (inbox_run["client_id"], sent_run["client_id"]) == ("", "tab-1")
    [told] = [e.data async for e in _until(service, after, "sent_on")]
    assert told["client_id"] == "tab-1" and told["from_thread_id"] == inbox.thread_id
    assert told["run_id"] == sent_run["run_id"] and told["channel"] == "web"
    dispatched = event_from_dict(told["dispatched"])
    assert isinstance(dispatched, Dispatched) and dispatched.thread_id == sent_run["thread_id"]
    assert dispatched.text == "plan my week"
    stop.set()
    await replaying


async def test_no_client_is_told_where_a_message_went_when_none_wrote_it(service, script, dispatch):
    inbox = Session("owner", "terminal", await service.inbox_thread("owner"))
    await service.hold_runs()
    await _kept(service, inbox, "plan my week")
    script.reply("Here's a plan.")
    after, stop = service.bus.last_id, asyncio.Event()
    replaying = asyncio.create_task(HeldRuns(service, RunHub(service.bus), {}).run(stop))
    service.release_runs()
    await _announced(service, after, 2)
    assert "sent_on" not in await _kinds(service, after, service.bus.last_id)
    stop.set()
    await replaying


async def _kinds(service, after: int, last: int) -> list[str]:
    """The kinds of the events after `after` up to `last`."""
    kinds = []
    async for event in service.bus.subscribe(after):
        kinds.append(event.kind)
        if event.id == last:
            return kinds
    raise AssertionError("the bus stopped")


async def _until(service, after: int, kind: str):
    """The first event of `kind` after `after`."""
    async with asyncio.timeout(5):
        async for event in service.bus.subscribe(after):
            if event.kind == kind:
                yield event
                return


async def test_a_chats_run_goes_to_its_chat_and_none_runs_while_runs_are_held(service, script):
    session = Session("owner", "telegram", await service.new_thread("owner"), Origin(held.CHAT, {"chat": "42"}))
    await service.hold_runs()
    await _kept(service, session, "from the chat")
    chats, stop = _Chats(), asyncio.Event()
    replaying = asyncio.create_task(HeldRuns(service, RunHub(service.bus), {held.CHAT: chats}).run(stop))
    await asyncio.sleep(0.05)
    assert chats.replayed == []  # still held: an update going back at start restarts after
    service.release_runs()
    async with asyncio.timeout(5):
        while not chats.replayed:
            await asyncio.sleep(0.01)
    assert chats.replayed == ["from the chat"]
    stop.set()
    await replaying
