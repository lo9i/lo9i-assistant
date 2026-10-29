"""The web app's build watched: a new build is told to the apps as a `web_build` event, once per version."""

import asyncio
import shutil
from pathlib import Path

from assistant.core.bus import EventBus
from assistant.daemon.web_build import WebBuildWatcher


def _build(directory: Path, version: str) -> None:
    (directory / "_app").mkdir(parents=True, exist_ok=True)
    (directory / "_app" / "version.json").write_text(f'{{"version":"{version}"}}')


async def _next_event(bus: EventBus) -> tuple[str, dict]:
    async for event in bus.subscribe(bus.last_id):
        return event.kind, event.data
    raise AssertionError("the bus ended")


async def test_a_new_build_is_told_to_the_apps_with_its_version(tmp_path):
    build = tmp_path / "webui"
    _build(build, "1")
    bus, stop = EventBus(), asyncio.Event()
    task = asyncio.create_task(WebBuildWatcher(bus, build).run(stop))
    try:
        await asyncio.sleep(0.3)  # The watch is set up before the build changes.
        waiting = asyncio.create_task(_next_event(bus))
        _build(build, "2")
        assert await asyncio.wait_for(waiting, timeout=10) == ("web_build", {"version": "2"})
        # A build replaces its folder whole.
        waiting = asyncio.create_task(_next_event(bus))
        shutil.rmtree(build)
        _build(build, "3")
        assert await asyncio.wait_for(waiting, timeout=10) == ("web_build", {"version": "3"})
    finally:
        stop.set()
        await asyncio.wait_for(task, timeout=5)


async def test_the_same_version_written_again_isnt_told(tmp_path):
    build = tmp_path / "webui"
    _build(build, "1")
    bus, stop = EventBus(), asyncio.Event()
    task = asyncio.create_task(WebBuildWatcher(bus, build).run(stop))
    try:
        await asyncio.sleep(0.3)
        _build(build, "1")
        (tmp_path / "other.txt").write_text("not the build")
        await asyncio.sleep(2.5)  # Past watchfiles' debounce.
        assert bus.last_id == 0
    finally:
        stop.set()
        await asyncio.wait_for(task, timeout=5)
