"""Connected clients: listed while their event stream is open, and the conversation each is on."""

import asyncio

import httpx

from assistant.core.bus import EventBus
from assistant.daemon.api import _bus_events, create_app, resume_point
from assistant.daemon.auth import trusted
from assistant.daemon.clients import ClientRegistry
from assistant.daemon.runs import RunHub
from assistant.protocol import CLIENT_HEADER


async def test_a_client_is_listed_while_it_reads_events(service):
    clients = ClientRegistry(service.bus, leave=lambda thread_id: None)
    service.bus.publish("memory")
    stream = _bus_events(service, 0, clients, ("abc", "cli", "unix socket"))
    await anext(stream)
    assert [(c.id, c.kind, c.transport) for c in clients.list()] == [("abc", "cli", "unix socket")]
    await stream.aclose()
    assert clients.list() == []


async def test_connecting_and_disconnecting_is_announced():
    bus = EventBus()
    clients = ClientRegistry(bus, leave=lambda thread_id: None)
    clients.remove(clients.add("abc", "cli", "unix socket"))
    kinds = []
    async for event in bus.subscribe():
        kinds.append(event.kind)
        if len(kinds) == 2:
            break
    assert kinds == ["clients", "clients"]


async def test_clients_route(service):
    app = create_app(service, RunHub())
    transport = httpx.ASGITransport(app=trusted(app))
    async with httpx.AsyncClient(
        transport=transport, base_url="http://127.0.0.1", headers={CLIENT_HEADER: "t"}
    ) as http:
        assert (await http.get("/clients")).json() == []


def _registry(grace_seconds: float = 0) -> tuple[ClientRegistry, list[str]]:
    left: list[str] = []
    return ClientRegistry(EventBus(), leave=left.append, grace_seconds=grace_seconds), left


async def test_moving_to_another_conversation_leaves_the_one_nobody_else_is_on():
    clients, left = _registry()
    clients.on_thread("a", "t1")
    clients.on_thread("b", "t1")
    clients.on_thread("a", "t2")
    assert left == []  # b is still on t1
    clients.on_thread("b", "t3")
    assert left == ["t1"]
    clients.on_thread("b", "t3")
    assert left == ["t1"]


async def test_disconnecting_leaves_the_conversation_unless_a_client_comes_back_to_it():
    clients, left = _registry()
    clients.on_thread("a", "t1")
    clients.remove(clients.add("a", "web", "127.0.0.1:1"))
    clients.on_thread("reloaded", "t1")  # the same page, reloaded within the grace period
    clients.on_thread("b", "t2")
    clients.remove(clients.add("b", "cli", "unix socket"))
    await asyncio.sleep(0.01)
    assert left == ["t2"]


async def test_a_client_with_another_connection_open_stays_on_its_conversation():
    clients, left = _registry()
    clients.on_thread("a", "t1")
    first = clients.add("a", "web", "127.0.0.1:1")
    clients.add("a", "web", "127.0.0.1:2")
    clients.remove(first)
    await asyncio.sleep(0.01)
    assert left == []


def test_a_new_event_stream_starts_from_now_and_a_reconnection_resumes():
    assert resume_point(last_id=57, last_event_id=None, after=None) == 57
    assert resume_point(last_id=57, last_event_id="40", after=None) == 40
    assert resume_point(last_id=57, last_event_id=None, after=0) == 0
