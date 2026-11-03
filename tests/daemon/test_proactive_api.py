"""The briefing, reviews and open loops through DaemonClient: the page, the settings, closing a loop, muting a kind,
and a briefing started now."""

import httpx
import pytest

from assistant.client.daemon_client import DaemonClient
from assistant.core.agent import LoopNotFoundError, ProactiveSettings
from assistant.core.proactive import loops
from assistant.core.proactive.model import LoopDraft
from assistant.daemon.api import create_app
from assistant.daemon.auth import trusted
from assistant.daemon.runs import RunHub
from assistant.protocol import CLIENT_HEADER


@pytest.fixture
async def client(service):
    transport = httpx.ASGITransport(app=trusted(create_app(service, RunHub())))
    async with httpx.AsyncClient(
        transport=transport, base_url="http://127.0.0.1", headers={CLIENT_HEADER: "t"}
    ) as http:
        yield DaemonClient(http)


async def test_the_page_starts_on_with_nothing_kept(client):
    page = await client.proactive.get()
    assert page.settings == ProactiveSettings() and page.loops == [] and page.briefing is None
    assert page.reviews == [] and page.running == []


async def test_settings_are_saved_and_a_wrong_time_refused(client):
    page = await client.proactive.save_settings(ProactiveSettings(briefing_time="07:30", weekly=False))
    assert (page.settings.briefing_time, page.settings.weekly) == ("07:30", False)
    with pytest.raises(httpx.HTTPStatusError):
        await client._transport.request("PUT", "/proactive/settings", json={"briefing_time": "7:30am"})


async def test_a_loop_is_closed_with_its_kind_muted_and_a_kind_unmuted(client, service):
    loop = await loops.add(service.store, "owner", LoopDraft(text="Answer Ana", kind="unanswered mail"), "briefing")
    assert loop is not None
    page = await client.proactive.close_loop(loop.id, "dismissed", stop_suggesting=True)
    assert page.loops[0].status == "dismissed" and page.settings.muted == ["unanswered mail"]
    assert (await client.proactive.mute("unanswered mail", muted=False)).settings.muted == []
    with pytest.raises(LoopNotFoundError):
        await client.proactive.close_loop("nope", "done")


async def test_a_briefing_started_now_is_the_days(client, service):
    await client.proactive.run("briefing")
    await service.proactive_runs.wait()
    page = await client.proactive.get()
    assert page.briefing is not None and page.briefing.status == "nothing" and page.running == []
