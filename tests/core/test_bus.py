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


async def test_memory_writes_publish_but_heartbeats_do_not(service, script):
    subscription = service.bus.subscribe(after=0)
    await service.telegram_heartbeat()
    script.call("remember", fact="dentist on Friday").reply("ok")
    await collect(service.send(await service.session("u", "cli"), "remember"))
    kinds = [e.kind for e in await _take(subscription, 3)]
    assert "memory" in kinds and "integrations" not in kinds
