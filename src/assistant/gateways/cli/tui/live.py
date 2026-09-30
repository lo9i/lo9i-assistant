"""Reacts to daemon events while the app is open: memory and skills reload the panel, jobs show a
notification, integration, client and job changes refresh an open screen, the active conversation follows
/new from another channel, a rename updates the title, runs started from another channel appear in the chat live, and a
conversation left with /new while its reply was running reports when it finishes."""

from collections.abc import Awaitable, Callable
from typing import Any, Protocol


class LiveApp(Protocol):
    def refresh_memory(self) -> Awaitable[None]: ...
    def reload_screen(self) -> Awaitable[None]: ...
    def refresh_title(self) -> Awaitable[None]: ...
    def follow_conversation(self) -> Awaitable[None]: ...
    def mirror_run(self, run: dict[str, Any]) -> None: ...
    def show_job(self, job: dict[str, Any]) -> None: ...
    def run_finished(self, run: dict[str, Any]) -> None: ...


def handlers(app: LiveApp) -> dict[str, Callable[[dict[str, Any]], Awaitable[None] | None]]:
    async def memory(_: dict[str, Any]) -> None:
        await app.refresh_memory()

    async def screen(_: dict[str, Any]) -> None:
        await app.reload_screen()

    async def threads(_: dict[str, Any]) -> None:
        await app.follow_conversation()

    async def settings(_: dict[str, Any]) -> None:
        await app.refresh_title()

    return {
        "memory": memory,
        "skills": memory,
        "integrations": screen,
        "clients": screen,
        "jobs": screen,
        "threads": threads,
        "settings": settings,
        "job": app.show_job,
        "run": app.mirror_run,
        "run_finished": app.run_finished,
    }
