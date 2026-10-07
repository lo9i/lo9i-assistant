"""Checking the extras for newer plugin versions: what counts as an update, the setting that turns
checks off, and the background checker."""

import asyncio
from pathlib import Path

import pytest

from assistant.core.agent import PluginUpdate
from assistant.core.repositories.known import EXTRAS
from tests.core.test_repositories import HELLO, REMOTE, repo  # noqa: F401 (a fixture, used by `extras`)


@pytest.fixture
def extras(repo: Path) -> Path:  # noqa: F811
    """The assistant's extras, the way the download sees them (test_repositories.py)."""
    return repo


def _release(extras, version: str) -> None:
    """Publish the hello server at `version` as the extras' next commit."""
    manifest = extras / "other" / "general" / "hello" / "server.yaml"
    text = manifest.read_text()
    old = next((line for line in text.splitlines() if line.startswith("version:")), None)
    manifest.write_text(text.replace(old, f"version: {version}") if old else f"version: {version}\n{text}")
    REMOTE["head"] = f"head-{version}"


async def _installed_hello(service, extras) -> None:
    _release(extras, "1.0.0")
    await service.install_from_repository(EXTRAS, [], [HELLO])


async def test_an_installed_plugin_with_a_newer_version_is_an_update(service, extras):
    await _installed_hello(service, extras)
    assert await service.plugin_updates() == []
    _release(extras, "1.1.0")
    await service.browse_repository(EXTRAS)
    assert await service.plugin_updates() == [PluginUpdate("server", "hello", "1.0.0", "1.1.0")]
    await service.update_mcp_server_from_repository("hello")
    assert await service.plugin_updates() == []


async def test_plugins_not_installed_or_without_versions_are_not_updates(service, extras):
    await service.install_from_repository(EXTRAS, ["expenses"], [])  # declares no version
    _release(extras, "2.0.0")  # hello isn't installed
    await service.browse_repository(EXTRAS)
    assert await service.plugin_updates() == []


async def test_checks_are_on_until_turned_off(service, extras):
    await _installed_hello(service, extras)
    _release(extras, "1.1.0")
    await service.browse_repository(EXTRAS)
    assert await service.plugin_update_checks()
    assert not await service.set_plugin_update_checks(False)
    assert not await service.plugin_update_checks()
    assert await service.plugin_updates() == []


async def test_the_checker_checks_at_start_and_a_new_listing_tells_clients(service, extras):
    events = service.bus.subscribe(service.bus.last_id)
    stop = asyncio.Event()
    running = asyncio.create_task(service.update_checker.run(stop))
    try:
        assert await _next_kind(events, "plugins") == "plugins"
        assert REMOTE["downloads"] == 1
    finally:
        stop.set()
        await running


async def test_the_checker_waits_while_off_and_checks_when_turned_on(service, extras):
    await service.set_plugin_update_checks(False)
    events = service.bus.subscribe(service.bus.last_id)
    stop = asyncio.Event()
    running = asyncio.create_task(service.update_checker.run(stop))
    try:
        await asyncio.sleep(0.05)
        assert REMOTE["downloads"] == 0
        await service.set_plugin_update_checks(True)
        assert await _next_kind(events, "plugins") == "plugins"
    finally:
        stop.set()
        await running


async def test_an_unreachable_extras_is_logged_and_waits(service, extras, caplog):
    REMOTE["head"] = None
    stop = asyncio.Event()
    running = asyncio.create_task(service.update_checker.run(stop))
    try:
        for _ in range(100):
            if any("plugin updates" in r.getMessage() for r in caplog.records):
                break
            await asyncio.sleep(0.02)
    finally:
        stop.set()
        await running
    assert any("Couldn't check lo9i/lo9i-assistant-extras for plugin updates" in r.getMessage() for r in caplog.records)


async def _next_kind(events, kind: str) -> str:
    async def wait() -> str:
        async for event in events:
            if event.kind == kind:
                return event.kind
        return ""

    return await asyncio.wait_for(wait(), timeout=5)
