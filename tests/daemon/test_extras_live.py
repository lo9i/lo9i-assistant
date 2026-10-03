"""The expenses extra, installed from its real repository: its MCP server answers and its page is
shown through the daemon. Needs the network and uv (`uv run pytest -m live`)."""

import asyncio
import shutil
import tempfile
from pathlib import Path

import httpx
import pytest

from assistant.core.agent import ServerValues
from assistant.core.mcp import folders, servers
from assistant.daemon.auth import COOKIE
from assistant.daemon.pages import create_pages_app

EXTRAS = "https://github.com/lo9i/lo9i-assistant-extras"


@pytest.fixture
def short_data_dir(monkeypatch):
    # Under /tmp: macOS limits socket paths to 104 characters, and pytest's tmp_path is longer.
    folder = tempfile.mkdtemp(dir="/tmp")
    monkeypatch.setattr("assistant.core.config.settings.mcp_data_dir", folder)
    yield Path(folder)
    shutil.rmtree(folder, ignore_errors=True)


@pytest.mark.live
async def test_expenses_installs_from_github_and_runs_with_its_page(service, short_data_dir):
    installed = await service.install_from_repository(EXTRAS, [], [ServerValues("expenses")])
    assert installed.servers[0].page and (await service.get_skill("expenses")).server == "expenses"
    server = await servers.load(service.store, "expenses")
    assert "month_summary" in {t.name for t in (await service.probe_mcp_server(server)).tools}
    assert (short_data_dir / "expenses" / "expenses.db").exists()

    stop = asyncio.Event()
    task = asyncio.create_task(service.pages.run(stop))
    try:
        async with asyncio.timeout(120):  # The first start builds the page's environment.
            while not folders.page_socket("expenses").exists():
                await asyncio.sleep(0.2)
        code = await service.open_device_pairing()
        _, token = await service.pair_device(code.code, "laptop", "127.0.0.1")
        transport = httpx.ASGITransport(app=create_pages_app(service), client=("127.0.0.1", 5000))
        async with httpx.AsyncClient(transport=transport, base_url="http://x", cookies={COOKIE: token}) as http:
            page = await http.get("/expenses/settings")
        assert page.status_code == 200 and '<base href="/expenses/">' in page.text
    finally:
        stop.set()
        await task
