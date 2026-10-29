"""Tells the apps when the web app's build changes (`npm run build`, an update installed): a `web_build` event with
its version, which every open tab answers by offering to reload (ConnectionBanner.svelte), so none goes on running
a build the daemon no longer serves."""

import asyncio
import json
import logging
from pathlib import Path

from watchfiles import Change, awatch

from assistant.core.bus import EventBus
from assistant.daemon.web_ui import BUILD_DIR

logger = logging.getLogger(__name__)


class WebBuildWatcher:
    name = "web build watcher"

    def __init__(self, bus: EventBus, directory: Path = BUILD_DIR) -> None:
        self._bus = bus
        self._directory = directory.resolve()
        self._version_file = self._directory / "_app" / "version.json"

    async def run(self, stop: asyncio.Event) -> None:
        served = await self._version()
        # A build replaces its folder whole, so the folder it sits in is watched.
        async for _ in awatch(self._directory.parent, stop_event=stop, watch_filter=self._is_version_file):
            version = await self._version()
            if version and version != served:
                served = version
                logger.info("The web app was built again (version %s); open tabs are offered to reload.", version)
                self._bus.publish("web_build", version=version)

    def _is_version_file(self, _change: Change, path: str) -> bool:
        return Path(path).resolve() == self._version_file

    async def _version(self) -> str:
        """The build's version, or "" while there's none (not built, or mid-build)."""
        try:
            text = await asyncio.to_thread(self._version_file.read_text)
            return str(json.loads(text)["version"])
        except (OSError, ValueError, KeyError, TypeError):
            return ""
