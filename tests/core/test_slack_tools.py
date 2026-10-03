"""Slack workspace tools: they need /slack, read through the user token, and posting needs approval."""

import pytest

import assistant.core.tools.slack as tools
from assistant.core.events import ApprovalRequired
from assistant.core.integrations.slack import connection
from tests.conftest import collect


class _Workspace:
    def __init__(self, client, timezone):
        pass

    async def search(self, query, count):
        return [f"#general · Ana · 2026-09-30 10:00 · ts=1.2\nabout {query}"]

    async def history(self, channel, thread, limit):
        return [f"Ana · 2026-09-30 10:00 · ts=1.2\nin {channel} {thread}"]

    async def post(self, channel, text, thread):
        _POSTED.append((channel, text, thread))
        return "https://acme.slack.com/archives/C1/p12"


_POSTED: list = []


@pytest.fixture
async def connected(service, monkeypatch):
    _POSTED.clear()
    monkeypatch.setattr(tools, "Workspace", _Workspace)
    await connection.save(service.store, connection.SlackConfig("xapp-1", "xoxb-1", "xoxp-1", "Acme", "U1", "ani"))


async def _run(service, script, on, tool, /, **args):
    script.call(tool, **args).reply("done")
    return await collect(service.send(await service.session("owner", on), "go"))


async def test_tools_point_to_the_setup_skill_until_slack_is_connected(service, script):
    events = await _run(service, script, "cli", "slack_search", query="budget")
    assert "Slack isn't set up" in events[1].output and "assistant-setup" in events[1].output


async def test_search_and_read(service, script, connected):
    events = await _run(service, script, "cli", "slack_search", query="budget")
    assert "about budget" in events[1].output
    events = await _run(service, script, "cli", "slack_read", channel="#general", thread="1.2")
    assert "in #general 1.2" in events[1].output


async def test_posting_asks_first(service, script, connected):
    events = await _run(service, script, "cli", "slack_post", channel="#general", text="Ship it")
    approval = next(e for e in events if isinstance(e, ApprovalRequired))
    assert approval.request["command"] == "In #general:\nShip it" and _POSTED == []
    session = await service.session("owner", "cli")
    events = await collect(service.resume(session, {approval.interrupt_id: {"approved": True, "reason": None}}))
    assert "Posted: https://acme.slack.com" in events[0].output and _POSTED == [("#general", "Ship it", None)]


async def test_posting_is_denied_in_scheduled_runs(service, script, connected):
    events = await _run(service, script, "worker", "slack_post", channel="#general", text="Ship it")
    assert "denied: unattended run" in events[1].output and _POSTED == []
