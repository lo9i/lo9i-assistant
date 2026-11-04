"""Messages waiting in a conversation are sent as runs of their own once its run ends, and at start."""

import asyncio

from lo9i.core.conversation import handoffs, queued
from lo9i.core.conversation.handoffs import Handoff
from lo9i.core.conversation.queued import Queued
from lo9i.daemon.queued import QueuedMessages
from lo9i.daemon.runs import Run, RunHub


class _Ending:
    """A restart or stop asked for (`asked`) or not; `consulted` once the messages asked whether one is."""

    def __init__(self, asked: bool = False) -> None:
        self.is_asked = asked
        self.consulted = asyncio.Event()

    def asked(self) -> bool:
        self.consulted.set()
        return self.is_asked


NOT_ENDING = _Ending()


class _Mirrors:
    """The runs shown in a chat channel's chat too."""

    def __init__(self) -> None:
        self.runs: list[Run] = []

    def mirror(self, run: Run) -> None:
        self.runs.append(run)


NO_MIRRORS = _Mirrors()


async def _announced(service, after: int, thread_id: str) -> dict:
    async with asyncio.timeout(10):
        async for event in service.bus.subscribe(after):
            if event.kind == "run" and event.data["thread_id"] == thread_id:
                return event.data
    raise AssertionError("the bus stopped")


async def test_a_waiting_message_is_sent_once_the_run_ends_and_one_left_at_start(service, script):
    mirrors = _Mirrors()
    left, waiting = "owner:left", "owner:waiting"
    await queued.add(service.store, "owner", left, Queued("web", "from before the restart"))
    after = service.bus.last_id
    stop = asyncio.Event()
    sending = asyncio.create_task(QueuedMessages(service, RunHub(service.bus), NOT_ENDING, mirrors).run(stop))
    run = await _announced(service, after, left)
    assert (run["text"], run["channel"], run["client_id"], run["notice"]) == ("from before the restart", "web", "", "")
    await queued.add(service.store, "owner", waiting, Queued("telegram", "the task"))
    after = service.bus.last_id
    service.bus.publish("run_finished", run_id="r1", thread_id=waiting, channel="web", status="ok", reply="")
    run = await _announced(service, after, waiting)
    assert (run["text"], run["channel"]) == ("the task", "telegram")
    # Each run is offered to the chat of its channel, which shows it when that's a chat channel.
    assert [(r.channel, r.text) for r in mirrors.runs] == [("web", "from before the restart"), ("telegram", "the task")]
    assert await service.queued_threads("owner") == []
    stop.set()
    await sending


async def test_a_follow_up_runs_at_once_where_nothing_runs_and_isnt_shown_as_the_users(service, script):
    from lo9i.core.conversation import ended

    stop = asyncio.Event()
    sending = asyncio.create_task(QueuedMessages(service, RunHub(service.bus), NOT_ENDING, NO_MIRRORS).run(stop))
    await ended.record(service.store, "owner", "owner:photos", "mcp:p:b", "The MCP server photos failed")
    script.reply("The conversion failed.")
    after = service.bus.last_id
    await queued.add(service.store, "owner", "owner:photos", Queued("web", "⚠️ photos: failed", True))
    run = await _announced(service, after, "owner:photos")
    # Announced with what it follows up on, which the apps show live where the user's message would be.
    assert (run["text"], run["notice"], run["channel"]) == ("", "⚠️ photos: failed", "web")
    stop.set()
    await sending


async def test_a_coding_task_is_announced_as_its_agents_brief(service, script):
    stop = asyncio.Event()
    sending = asyncio.create_task(QueuedMessages(service, RunHub(service.bus), NOT_ENDING, NO_MIRRORS).run(stop))
    await handoffs.hand(service.store, "owner", "owner:fix", Handoff("claude-code", "claude", "Claude Code", "/tmp"))
    after = service.bus.last_id
    await queued.add(service.store, "owner", "owner:fix", Queued("web", "finish", brief="Claude Code"))
    run = await _announced(service, after, "owner:fix")
    # The assistant wrote it: the apps show it as the agent's task, never as the user's message.
    assert (run["text"], run["brief"]) == ("finish", "Claude Code")
    stop.set()
    await sending


async def test_waiting_messages_wait_while_a_restart_is_asked_for_and_go_once_its_taken_back(service, script):
    ending = _Ending(asked=True)
    await queued.add(service.store, "owner", "owner:later", Queued("web", "the task"))
    stop = asyncio.Event()
    sending = asyncio.create_task(QueuedMessages(service, RunHub(service.bus), ending, NO_MIRRORS).run(stop))
    await asyncio.wait_for(ending.consulted.wait(), 10)
    assert await service.queued_threads("owner") == ["owner:later"]  # kept for after the restart
    ending.is_asked = False
    after = service.bus.last_id
    service.bus.publish("ending", ending="restart", waiting_for_runs=0, taken_back=True)
    run = await _announced(service, after, "owner:later")
    assert run["text"] == "the task"
    stop.set()
    await sending


async def test_while_a_restart_is_asked_for_a_conversation_whose_messages_go_first_is_sent_and_then_let_go(
    service, script
):
    ending = _Ending(asked=True)
    service.ending.send_first("owner:now")
    await queued.add(service.store, "owner", "owner:now", Queued("web", "the task sent now"))
    await queued.add(service.store, "owner", "owner:later", Queued("web", "the task for later"))
    script.reply("On it.")
    after = service.bus.last_id
    stop = asyncio.Event()
    sending = asyncio.create_task(QueuedMessages(service, RunHub(service.bus), ending, NO_MIRRORS).run(stop))
    run = await _announced(service, after, "owner:now")
    assert run["text"] == "the task sent now"
    # Once its run ended with nothing left there, the restart waits for it no more; the other still waits.
    await asyncio.wait_for(service.ending.until_sent(), 10)
    assert not service.ending.goes_first("owner:now")
    assert await service.queued_threads("owner") == ["owner:later"]
    stop.set()
    await sending


async def test_a_task_kept_for_after_a_restart_goes_with_its_handoff_once_the_daemon_is_back(service, script):
    handoff = Handoff("claude-code", "claude", "Claude Code", "/tmp")
    await queued.add(service.store, "owner", "owner:fix", Queued("web", "finish", brief="Claude Code", hand_to=handoff))
    after = service.bus.last_id
    stop = asyncio.Event()
    sending = asyncio.create_task(QueuedMessages(service, RunHub(service.bus), NOT_ENDING, NO_MIRRORS).run(stop))
    run = await _announced(service, after, "owner:fix")
    assert (run["text"], run["brief"]) == ("finish", "Claude Code")
    assert await handoffs.current(service.store, "owner", "owner:fix") == handoff
    stop.set()
    await sending


async def test_a_task_held_past_a_take_back_is_never_run_as_the_users_message(service, script):
    await queued.add(service.store, "owner", "owner:back", Queued("web", "finish", brief="Claude Code"))
    after = service.bus.last_id
    stop = asyncio.Event()
    sending = asyncio.create_task(QueuedMessages(service, RunHub(service.bus), NOT_ENDING, NO_MIRRORS).run(stop))
    async with asyncio.timeout(10):
        while not await service.notifications("owner"):
            await asyncio.sleep(0.01)
    stop.set()
    await sending
    runs = [e async for e in _until_now(service, after) if e.kind == "run" and e.data["thread_id"] == "owner:back"]
    assert runs == [] and await service.queued_threads("owner") == []
    assert (await service.notifications("owner"))[0].title == "Task not sent"


async def _until_now(service, after: int):
    last = service.bus.last_id
    async for event in service.bus.subscribe(after):
        yield event
        if event.id >= last:
            return
