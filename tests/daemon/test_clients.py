"""Connected clients: listed while their event stream is open."""

import httpx

from assistant.core.bus import EventBus
from assistant.daemon.api import _bus_events, create_app
from assistant.daemon.clients import ClientRegistry
from assistant.daemon.runs import RunHub
from assistant.protocol import CLIENT_HEADER


async def test_a_client_is_listed_while_it_reads_events(service):
    clients = ClientRegistry(service.bus)
    service.bus.publish("memory")
    stream = _bus_events(service, 0, clients, ("abc", "cli", "unix socket"))
    await anext(stream)
    assert [(c.id, c.kind, c.transport) for c in clients.list()] == [("abc", "cli", "unix socket")]
    await stream.aclose()
    assert clients.list() == []


async def test_connecting_and_disconnecting_is_announced():
    bus = EventBus()
    clients = ClientRegistry(bus)
    clients.remove(clients.add("abc", "cli", "unix socket"))
    kinds = []
    async for event in bus.subscribe():
        kinds.append(event.kind)
        if len(kinds) == 2:
            break
    assert kinds == ["clients", "clients"]


async def test_clients_route(service):
    app = create_app(service, RunHub())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://lo9i", headers={CLIENT_HEADER: "t"}) as http:
        assert (await http.get("/clients")).json() == []
