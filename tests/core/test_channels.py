"""Chat channels installed as plugins: the hub their processes connect to, the processes, the
prompt's Channels section, and the old Telegram and Slack settings handed to the plugins."""

import asyncio
import json
import sys

import pytest

from assistant.core.approvals import RemoteApprovals
from assistant.core.bus import EventBus
from assistant.core.channels import hub as hub_module
from assistant.core.channels import legacy
from assistant.core.channels.hub import ChannelHub, ChannelNotConnectedError, SetupItem
from assistant.core.channels.processes import ChannelProcesses
from assistant.core.conversation.prompt import build_system_prompt
from assistant.core.mcp import folders, servers
from assistant.core.mcp.install import ServerValues
from assistant.core.mcp.servers import McpServer, McpServerError
from assistant.core.outbox import DeliveryError, Outbox


def _hub(name: str = "lo9i") -> tuple[ChannelHub, Outbox, RemoteApprovals, EventBus]:
    outbox, approvals, bus = Outbox(), RemoteApprovals(), EventBus()

    async def assistant_name() -> str:
        return name

    return ChannelHub(outbox, approvals, bus, assistant_name), outbox, approvals, bus


async def _attached(hub: ChannelHub, channel: str):
    """The channel's stream, past its hello."""
    stream = hub.attach(channel)
    hello = await anext(stream)
    assert hello.kind == "hello" and hello.data == {"assistant_name": "lo9i"}
    return stream


async def test_a_connected_channel_delivers_messages_it_confirms():
    hub, outbox, approvals, _ = _hub()
    stream = await _attached(hub, "telegram")
    assert outbox.channels == ["telegram"] and approvals.available
    sending = asyncio.create_task(outbox.send("telegram", "stretch"))
    event = await anext(stream)
    assert (event.kind, event.data["text"]) == ("deliver", "stretch")
    assert hub.confirm(event.data["id"], "")
    await sending
    assert not hub.confirm(event.data["id"], "")  # nothing waits any more


async def test_a_delivery_the_channel_refuses_or_doesnt_confirm_fails(monkeypatch):
    hub, outbox, _, _ = _hub()
    stream = await _attached(hub, "telegram")
    sending = asyncio.create_task(outbox.send("telegram", "hi"))
    hub.confirm((await anext(stream)).data["id"], "Telegram said no")
    with pytest.raises(DeliveryError, match="Telegram said no"):
        await sending
    monkeypatch.setattr(hub_module, "DELIVERY_SECONDS", 0.05)
    with pytest.raises(DeliveryError, match="in time"):
        await outbox.send("telegram", "hi")


async def test_a_job_approval_goes_to_the_channel_and_its_answer_back():
    hub, _, approvals, _ = _hub()
    stream = await _attached(hub, "telegram")
    asking = asyncio.create_task(approvals.ask("i1", "The job news", {"command": "rm x"}, timeout=5))
    event = await anext(stream)
    assert (event.kind, event.data["interrupt_id"], event.data["title"]) == ("approval", "i1", "The job news")
    hub.confirm(event.data["id"], "")
    await asyncio.sleep(0)
    assert approvals.answer("i1", {"approved": True, "reason": ""})
    assert await asking == {"approved": True, "reason": ""}


async def test_a_channel_that_disconnects_is_unregistered_and_its_deliveries_fail():
    hub, outbox, approvals, _ = _hub()
    stream = await _attached(hub, "telegram")
    hub.set_status("telegram", [SetupItem("text", "Bot: @lo9i_bot")])
    sending = asyncio.create_task(outbox.send("telegram", "hi"))
    await anext(stream)
    await stream.aclose()
    with pytest.raises(DeliveryError, match="disconnected"):
        await sending
    assert (outbox.channels, approvals.available, hub.connected("telegram")) == ([], False, False)
    assert hub.items("telegram") == []
    with pytest.raises(ChannelNotConnectedError):
        hub.act("telegram", "new-pairing-code")


async def test_a_second_stream_replaces_the_first():
    hub, outbox, _, _ = _hub()
    first = await _attached(hub, "telegram")
    second = await _attached(hub, "telegram")
    with pytest.raises(StopAsyncIteration):
        await anext(first)
    assert outbox.channels == ["telegram"]
    hub.act("telegram", "new-pairing-code")
    assert (await anext(second)).data == {"action": "new-pairing-code"}


async def test_channels_hear_when_the_assistant_is_renamed():
    names = ["lo9i"]
    outbox, approvals, bus = Outbox(), RemoteApprovals(), EventBus()

    async def assistant_name() -> str:
        return names[-1]

    hub = ChannelHub(outbox, approvals, bus, assistant_name)
    stop = asyncio.Event()
    running = asyncio.create_task(hub.run(stop))
    stream = aiter(hub.attach("telegram"))
    await anext(stream)
    await asyncio.sleep(0.01)
    names.append("Ada")
    bus.publish("settings")
    assert (await anext(stream)).data == {"assistant_name": "Ada"}
    stop.set()
    await running


def test_tokens_name_their_channel_until_replaced_or_revoked():
    hub, *_ = _hub()
    first = hub.issue_token("telegram")
    second = hub.issue_token("telegram")
    assert (hub.channel_for(first), hub.channel_for(second)) == (None, "telegram")
    hub.revoke("telegram")
    assert hub.channel_for(second) is None


async def test_the_channel_process_runs_with_the_daemons_address_and_its_token(service, isolated_settings):
    out = isolated_settings / "env.json"
    script = (
        "import json, os; "
        f"json.dump({{k: v for k, v in os.environ.items() if k.startswith(('LO9I', 'BOT'))}}, open({str(out)!r}, 'w'))"
    )
    server = McpServer("telegram", env={"BOT": "b"}, channel_command=sys.executable, channel_args=["-c", script])
    await servers.save(service.store, server)
    processes = ChannelProcesses(service.store, service.channels_hub)
    stop = asyncio.Event()
    running = asyncio.create_task(processes.run(stop))
    for _ in range(200):
        if out.exists() and out.read_text():
            break
        await asyncio.sleep(0.02)
    stop.set()
    await running
    env = json.loads(out.read_text())
    assert (env["LO9I_CHANNEL"], env["BOT"]) == ("telegram", "b")
    assert env["LO9I_URL"].startswith("http://127.0.0.1:")
    assert service.channels_hub.channel_for(env["LO9I_CHANNEL_TOKEN"]) is None  # revoked once stopped


def test_a_plugin_is_an_mcp_server_a_channel_or_both():
    servers.validate(McpServer("telegram", channel_command="uv"))
    servers.validate(McpServer("slack", command="uv", channel_command="uv"))
    assert McpServer("telegram", channel_command="uv").transport == "none"
    with pytest.raises(McpServerError, match="Give either"):
        servers.validate(McpServer("nothing"))


async def test_the_prompt_says_how_to_write_on_each_installed_channel(service):
    style = "A phone chat. Short messages."
    await servers.save(service.store, McpServer("telegram", channel_command="uv", channel_style=style))
    await servers.save(service.store, McpServer("off", channel_command="uv", channel_style="Never", enabled=False))
    prompt = await build_system_prompt(service.store, "owner", "", "")
    assert f"- telegram: {style}" in prompt and "Never" not in prompt
    assert "- web: " in prompt


async def test_the_old_telegram_settings_go_to_the_plugin(service):
    record = {"token": "123:abc", "bot_username": "lo9i_bot", "users": [{"id": 7, "name": "Ana"}]}
    await service.store.aput(("integrations",), "telegram", record)
    await service.store.aput(("integrations",), "telegram_heartbeat", {"at": "2026-10-01T00:00:00+00:00"})
    assert await legacy.known_fields(service.store, "telegram") == ["TELEGRAM_TOKEN"]
    filled = await legacy.fill(service.store, ServerValues("telegram", {"TELEGRAM_TOKEN": ""}))
    assert filled.values == {"TELEGRAM_TOKEN": "123:abc"}
    given = await legacy.fill(service.store, ServerValues("telegram", {"TELEGRAM_TOKEN": "new"}))
    assert given.values == {"TELEGRAM_TOKEN": "new"}
    await legacy.hand_over(service.store, "telegram")
    imported = json.loads((folders.data("telegram") / legacy.IMPORT_FILE).read_text())
    assert imported == {"users": [{"id": 7, "name": "Ana"}]}
    assert await service.store.aget(("integrations",), "telegram") is None
    assert await service.store.aget(("integrations",), "telegram_heartbeat") is None


async def test_the_old_slack_tokens_fill_the_plugins_fields(service):
    record = {"app_token": "xapp-1", "bot_token": "xoxb-1", "user_token": "xoxp-1", "owner_id": "U1"}
    await service.store.aput(("integrations",), "slack", record)
    filled = await legacy.fill(service.store, ServerValues("slack", {}))
    assert filled.values == {"SLACK_APP_TOKEN": "xapp-1", "SLACK_BOT_TOKEN": "xoxb-1", "SLACK_USER_TOKEN": "xoxp-1"}
    await legacy.hand_over(service.store, "slack")
    assert await service.store.aget(("integrations",), "slack") is None
    assert await legacy.known_fields(service.store, "other") == []


async def test_a_channel_plugin_is_installed_with_its_library_and_the_old_settings(
    service, isolated_settings, monkeypatch
):
    import shutil
    from pathlib import Path

    from assistant.core.repositories import checkout

    remote = isolated_settings / "remote"
    (remote / "lib" / "lo9i-chat").mkdir(parents=True)
    (remote / "lib" / "lo9i-chat" / "pyproject.toml").write_text("[project]\nname = 'lo9i-chat'\n")
    (remote / "mcp" / "telegram").mkdir(parents=True)
    (remote / "mcp" / "telegram" / "server.yaml").write_text(
        "libraries: [lo9i-chat]\n"
        "env: {TELEGRAM_DATA: '{data}'}\n"
        "fields: [{key: TELEGRAM_TOKEN, label: Bot token, secret: true}]\n"
        "channel: {command: '{python}', args: ['{dir}/main.py'], style: A phone chat.}\n"
    )

    async def fetch(url: str, dest: Path) -> str:
        shutil.copytree(remote, dest)
        return "c1"

    async def latest_commit(url: str) -> str:
        return "c1"

    monkeypatch.setattr(checkout, "_fetch", fetch)
    monkeypatch.setattr(checkout, "latest_commit", latest_commit)
    await service.store.aput(("integrations",), "telegram", {"token": "123:abc", "users": [{"id": 7, "name": "Ana"}]})
    url = "https://example.com/me/extras.git"
    found = (await service.browse_repository(url)).servers[0]
    assert (found.channel, found.transport, found.known_fields) == (True, "none", ["TELEGRAM_TOKEN"])
    installed = await service.install_from_repository(url, [], [ServerValues("telegram", {"TELEGRAM_TOKEN": ""})])
    assert installed.servers[0].channel
    server = await servers.load(service.store, "telegram")
    assert server.env == {"TELEGRAM_DATA": str(folders.data("telegram")), "TELEGRAM_TOKEN": "123:abc"}
    assert server.channel_args == [f"{folders.code('telegram')}/main.py"]
    assert (folders.library("lo9i-chat") / "pyproject.toml").is_file()
    assert folders.library("lo9i-chat") == folders.code("telegram").parent.parent / "lib" / "lo9i-chat"
    assert (folders.data("telegram") / legacy.IMPORT_FILE).is_file()
    assert [c.name for c in await service.channels()] == ["telegram"]
