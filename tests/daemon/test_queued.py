"""Messages waiting in a conversation are sent as runs of their own once its run ends, and at start."""

import asyncio

from assistant.core.conversation import queued
from assistant.core.conversation.queued import Queued
from assistant.daemon.queued import QueuedMessages
from assistant.daemon.runs import RunHub


async def _announced(service, after: int, thread_id: str) -> dict:
    async with asyncio.timeout(10):
        async for event in service.bus.subscribe(after):
            if event.kind == "run" and event.data["thread_id"] == thread_id:
                return event.data
    raise AssertionError("the bus stopped")


async def test_a_waiting_message_is_sent_once_the_run_ends_and_one_left_at_start(service, script):
    left, waiting = "owner:left", "owner:waiting"
    await queued.add(service.store, "owner", left, Queued("web", "from before the restart"))
    after = service.bus.last_id
    stop = asyncio.Event()
    sending = asyncio.create_task(QueuedMessages(service, RunHub(service.bus)).run(stop))
    run = await _announced(service, after, left)
    assert (run["text"], run["channel"], run["client_id"]) == ("from before the restart", "web", "")
    await queued.add(service.store, "owner", waiting, Queued("telegram", "the task"))
    after = service.bus.last_id
    service.bus.publish("run_finished", run_id="r1", thread_id=waiting, channel="web", status="ok", reply="")
    run = await _announced(service, after, waiting)
    assert (run["text"], run["channel"]) == ("the task", "telegram")
    assert await service.queued_threads("owner") == []
    stop.set()
    await sending


async def test_a_follow_up_runs_at_once_where_nothing_runs_and_isnt_shown_as_the_users(service, script):
    from assistant.core.conversation import ended

    stop = asyncio.Event()
    sending = asyncio.create_task(QueuedMessages(service, RunHub(service.bus)).run(stop))
    await ended.record(service.store, "owner", "owner:photos", "mcp:p:b", "The MCP server photos failed")
    script.reply("The conversion failed.")
    after = service.bus.last_id
    await queued.add(service.store, "owner", "owner:photos", Queued("web", "⚠️ photos: failed", True))
    run = await _announced(service, after, "owner:photos")
    assert (run["text"], run["channel"]) == ("", "web")
    stop.set()
    await sending
