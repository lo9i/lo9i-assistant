import httpx
import pytest

from lo9i.client.daemon_client import DaemonClient
from lo9i.core.agent import SandboxUnavailableError
from lo9i.core.sandbox import runtime as runtimes
from lo9i.daemon.api import create_app
from lo9i.daemon.auth import trusted
from lo9i.daemon.runs import RunHub
from lo9i.protocol import CLIENT_HEADER


@pytest.fixture
async def client(service, monkeypatch, tmp_path):
    monkeypatch.setattr(runtimes, "_SEARCHED", str(tmp_path / "nothing"))
    transport = httpx.ASGITransport(app=trusted(create_app(service, RunHub())))
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1", headers={CLIENT_HEADER: "t"}) as h:
        yield DaemonClient(h)


async def test_without_a_runtime_it_says_so_and_cant_be_turned_on(client):
    status = await client.sandbox.status()
    assert (status.enabled, status.available, status.runtime) == (False, False, "")
    assert "Neither Docker nor Podman" in status.problem and status.fix
    with pytest.raises(SandboxUnavailableError, match="Neither Docker nor Podman"):
        await client.sandbox.set_enabled(True)
    assert (await client.sandbox.set_enabled(False)).enabled is False
