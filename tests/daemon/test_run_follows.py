"""Runs followed over a client's /events stream instead of a stream each (daemon/run_follows.py)."""

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from assistant.core.events import Done, TextDelta
from assistant.daemon.api import create_app
from assistant.daemon.auth import trusted
from assistant.daemon.run_follows import RUN_END, RUN_EVENTS, RunFollows
from assistant.daemon.runs import RunHub
from assistant.protocol import CLIENT_HEADER, CLIENT_ID_HEADER

KEY = ("dev1", "tab-1")


async def _words(*words: str, wait: asyncio.Event | None = None):
    for word in words:
        await asyncio.sleep(0)
        yield TextDelta(word)
    if wait is not None:
        await wait.wait()
    yield Done()


async def _quiet() -> AsyncIterator[dict[str, Any]]:
    await asyncio.Event().wait()
    yield {}


async def _until_end(stream: AsyncIterator[dict[str, Any]]) -> list[tuple[str, dict[str, Any]]]:
    got = []
    async for sent in stream:
        got.append((sent["event"], json.loads(sent["data"])))
        if sent["event"] == RUN_END:
            return got
    return got


def _texts(got: list[tuple[str, dict[str, Any]]]) -> list[str]:
    return [e.get("text", e["type"]) for kind, data in got if kind == RUN_EVENTS for e in data["events"]]


async def test_a_run_followed_before_the_stream_opens_comes_down_it():
    hub = RunHub()
    follows = RunFollows(hub)
    follows.follow(KEY, "f1", hub.start("t", _words("a", "b")), 0)
    got = await _until_end(follows.events(KEY, _quiet()))
    assert _texts(got) == ["a", "b", "Done"]
    assert got[-1] == (RUN_END, {"follow": "f1"})


async def test_each_batch_says_how_many_events_came_before_it():
    hub = RunHub()
    run = hub.start("t", _words("a", "b"))
    await anext(hub.follow(run, 2))  # the run is finished
    follows = RunFollows(hub)
    follows.follow(KEY, "f1", run, 1)
    got = await _until_end(follows.events(KEY, _quiet()))
    assert got[0] == (
        RUN_EVENTS,
        {"follow": "f1", "after": 1, "events": [{"type": "TextDelta", "text": "b"}, {"type": "Done"}]},
    )


async def test_bus_events_come_down_the_same_stream():
    async def bus() -> AsyncIterator[dict[str, Any]]:
        yield {"id": "7", "event": "memory", "data": "{}"}
        await asyncio.Event().wait()

    stream = RunFollows(RunHub()).events(KEY, bus())
    assert await anext(stream) == {"id": "7", "event": "memory", "data": "{}"}
    await stream.aclose()


async def test_another_clients_stream_gets_nothing():
    hub = RunHub()
    follows = RunFollows(hub)
    other = follows.events(("dev1", "tab-2"), _quiet())
    follows.follow(KEY, "f1", hub.start("t", _words("a")), 0)
    try:
        await asyncio.wait_for(anext(other), 0.05)
    except TimeoutError:
        pass
    else:
        raise AssertionError("another client's stream got a run it didn't follow")
    finally:
        await other.aclose()


async def test_a_new_stream_takes_over_and_an_older_one_closing_late_leaves_it_be():
    hub = RunHub()
    follows = RunFollows(hub)
    go_on = asyncio.Event()
    run = hub.start("t", _words("a", wait=go_on))
    follows.follow(KEY, "f1", run, 0)
    old = follows.events(KEY, _quiet())
    assert (await anext(old))["event"] == RUN_EVENTS
    new = follows.events(KEY, _quiet())
    first = asyncio.ensure_future(anext(new))
    await asyncio.sleep(0)
    await old.aclose()
    go_on.set()
    got = [json.loads((await first)["data"])] + [data for _, data in await _until_end(new)]
    assert [e["type"] for d in got for e in d.get("events", [])] == ["TextDelta", "Done"]


async def test_what_a_client_followed_is_forgotten_once_it_stays_away():
    hub = RunHub()
    follows = RunFollows(hub, grace_seconds=0)
    run = hub.start("t", _words("a", wait=asyncio.Event()))
    follows.follow(KEY, "f1", run, 0)
    stream = follows.events(KEY, _quiet())
    await anext(stream)
    await stream.aclose()
    await asyncio.sleep(0.01)
    assert follows._follows == {}


async def test_the_routes_follow_and_stop_following(service):
    hub = RunHub()
    app = trusted(create_app(service, hub))
    headers = {CLIENT_HEADER: "web", CLIENT_ID_HEADER: "tab-1"}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t", headers=headers) as http:
        assert (await http.put("/events/runs/f1", json={"run_id": "nope"})).status_code == 404
        run = hub.start("t", _words("a", wait=asyncio.Event()))
        assert (await http.put("/events/runs/f1", json={"run_id": run.id, "after": 0})).status_code == 200
        assert (await http.delete("/events/runs/f1")).status_code == 200
        unnamed = await http.put("/events/runs/f1", json={"run_id": run.id}, headers={CLIENT_ID_HEADER: ""})
        assert unnamed.status_code == 400
