"""Which runs the app shows that it isn't streaming itself: those in progress in a conversation it opens,
shown from their start after its history, and those announced while it's there (`run` events). Each shows
once, and none before the history it follows has loaded, as in the web app (lib/chat/controller.ts)."""

import asyncio
from typing import Any


class FollowedRuns:
    def __init__(self) -> None:
        self._followed: set[str] = set()
        self._loaded = asyncio.Event()
        self._loaded.set()

    def loading(self) -> None:
        """A conversation's history is loading: the runs shown so far were the last one's."""
        self._followed = set()
        self._loaded.clear()

    def loaded(self) -> None:
        self._loaded.set()

    async def unseen(self, runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """The runs not shown yet, once the history has loaded; from now on they count as shown."""
        await self._loaded.wait()
        fresh = [run for run in runs if run["run_id"] not in self._followed]
        self._followed |= {run["run_id"] for run in fresh}
        return fresh
