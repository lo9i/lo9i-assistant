"""The event bus and the events the store publishes when things change."""

import asyncio

from assistant.core.bus import EventBus
from tests.conftest import collect


async def _take(subscription, count):
    return [await asyncio.wait_for(anext(subscription), 1) for _ in range(count)]


async def test_subscribers_get_missed_events_then_live_ones():
    bus = EventBus()
    bus.publish("memory")
    subscription = bus.subscribe(after=0)
    first = await _take(subscription, 1)
    bus.publish("jobs", name="daily")
    second = await _take(subscription, 1)
    assert [e.kind for e in first + second] == ["memory", "jobs"] and second[0].data == {"name": "daily"}
    resumed = await _take(bus.subscribe(after=first[0].id), 1)
    assert resumed[0].kind == "jobs"


async def test_a_client_reconnecting_after_a_restart_gets_the_new_runs_events():
    """It sends the last id it got from the previous run; the new run's ids must come after it."""
    before = EventBus()
    for _ in range(3):
        before.publish("memory")
    after_restart = EventBus()
    after_restart.publish("devices")
    resumed = await _take(after_restart.subscribe(after=before.last_id), 1)
    assert resumed[0].kind == "devices"


async def test_memory_writes_publish(service, script):
    subscription = service.bus.subscribe(after=0)
    script.call("remember", fact="dentist on Friday").reply("ok")
    await collect(service.send(await service.session("u", "cli"), "remember"))
    # threads, conversations, settings (the get-to-know-you offer, decided on the first message), memory
    kinds = [e.kind for e in await _take(subscription, 4)]
    assert "memory" in kinds
