import asyncio

from assistant.core.events import Done, TextDelta
from assistant.daemon.runs import RunHub


async def _events():
    for word in ["a", "b"]:
        await asyncio.sleep(0)
        yield TextDelta(word)
    yield Done()


async def test_follow_replays_from_an_id_and_ends():
    hub = RunHub()
    run = hub.start("t", _events())
    everything = [(i, e) async for i, e in hub.follow(run, 0)]
    assert [e["type"] if e else None for _, e in everything] == ["TextDelta", "TextDelta", "Done", None]
    from_two = [(i, e) async for i, e in hub.follow(run, 2)]
    assert [i for i, _ in from_two] == [3, 4] and from_two[-1][1] is None


async def test_a_failing_run_reports_an_error():
    async def broken():
        yield TextDelta("x")
        raise RuntimeError("boom")

    hub = RunHub()
    run = hub.start("t", broken())
    events = [e async for _, e in hub.follow(run, 0) if e]
    assert events[-1] == {"type": "Error", "message": "RuntimeError: boom"}


async def test_starting_a_run_is_announced_on_the_bus():
    from assistant.core.bus import EventBus

    bus = EventBus()
    run = RunHub(bus).start("t1", _events(), channel="web", client_id="tab-1", text="hi")
    event = await anext(bus.subscribe())
    assert event.kind == "run" and event.data == {
        "run_id": run.id,
        "thread_id": "t1",
        "channel": "web",
        "client_id": "tab-1",
        "text": "hi",
        "notice": "",
    }


async def test_finishing_a_run_is_announced_with_an_excerpt():
    from assistant.core.bus import EventBus

    bus = EventBus()
    run = RunHub(bus).start("t1", _events(), channel="cli")
    events = bus.subscribe()
    kinds = [await anext(events), await anext(events)]
    assert kinds[1].kind == "run_finished"
    assert kinds[1].data == {"run_id": run.id, "thread_id": "t1", "channel": "cli", "status": "ok", "reply": "ab"}


async def test_a_cancelled_run_is_announced_as_cancelled():
    from assistant.core.bus import EventBus
    from assistant.core.events import Cancelled

    async def stopped():
        yield TextDelta("a")
        yield Cancelled()

    bus = EventBus()
    RunHub(bus).start("t1", stopped(), channel="cli")
    events = bus.subscribe()
    finished = [await anext(events), await anext(events)][1]
    assert finished.kind == "run_finished" and finished.data["status"] == "cancelled"


async def test_only_runs_in_progress_are_listed_as_running():
    hub = RunHub()
    release = asyncio.Event()

    async def waiting():
        await release.wait()
        yield Done()

    done, waits = hub.start("t1", _events()), hub.start("t2", waiting())
    [_ async for _ in hub.follow(done, 0)]
    assert hub.running() == [waits]
    release.set()
    [_ async for _ in hub.follow(waits, 0)]
    assert hub.running() == []
