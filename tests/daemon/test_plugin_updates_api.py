"""Updating a plugin over the API: a new version that needs a value not given yet answers 409, so the apps ask for it
and send it with the update."""

import httpx

from assistant.daemon.api import create_app
from assistant.daemon.auth import trusted
from assistant.daemon.runs import RunHub
from assistant.protocol import CLIENT_HEADER
from tests.core.test_repositories import _MANIFEST, HELLO, URL, repo  # noqa: F401 (a fixture)


async def test_an_update_that_needs_a_value_answers_409_and_goes_once_its_given(service, repo):  # noqa: F811
    await service.install_from_repository(URL, [], [HELLO])
    (repo / "other" / "general" / "hello" / "server.yaml").write_text(
        _MANIFEST + "  - {key: HELLO_CITY, label: Your city}\n"
    )
    transport = httpx.ASGITransport(app=trusted(create_app(service, RunHub())))
    async with httpx.AsyncClient(
        transport=transport, base_url="http://127.0.0.1", headers={CLIENT_HEADER: "t"}
    ) as http:
        needs = await http.post("/mcp/servers/hello/update")
        assert (needs.status_code, needs.json()["detail"]) == (
            409,
            "The new version of hello needs Your city: remove it and install it again.",
        )
        unknown = await http.post("/mcp/servers/hello/update", json={"values": {"HELLO_TOWN": "Rosario"}})
        assert unknown.status_code == 400
        updated = await http.post("/mcp/servers/hello/update", json={"values": {"HELLO_CITY": "Rosario"}})
        assert updated.status_code == 200
