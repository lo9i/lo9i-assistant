"""Reacts to daemon events while the app is open: memory and skills reload the panel, finished jobs,
MCP servers or skills that keep failing and MCP servers whose sign-in stopped working show a
notification, integration, client, job and settings changes refresh an open screen, a rename updates
the title, runs started elsewhere in this conversation appear in the chat live, and a conversation
left with /new while its reply was running reports when it finishes."""

from collections.abc import Awaitable, Callable
from typing import Any, Protocol


class LiveApp(Protocol):
    def refresh_memory(self) -> Awaitable[None]: ...
    def reload_screen(self) -> Awaitable[None]: ...
    def refresh_title(self) -> Awaitable[None]: ...
    def mirror_run(self, run: dict[str, Any]) -> None: ...
    def show_job(self, job: dict[str, Any]) -> None: ...
    def show_failing(self, failing: dict[str, Any]) -> None: ...
    def show_signed_out(self, signed_out: dict[str, Any]) -> None: ...
    def run_finished(self, run: dict[str, Any]) -> None: ...


def handlers(app: LiveApp) -> dict[str, Callable[[dict[str, Any]], Awaitable[None] | None]]:
    async def memory(_: dict[str, Any]) -> None:
        await app.refresh_memory()

    async def screen(_: dict[str, Any]) -> None:
        await app.reload_screen()

    async def settings(_: dict[str, Any]) -> None:
        await app.refresh_title()
        await app.reload_screen()

    return {
        "memory": memory,
        "skills": memory,
        "integrations": screen,
        "clients": screen,
        "jobs": screen,
        "conversations": screen,
        "devices": screen,
        "mcp": screen,
        "settings": settings,
        "job": app.show_job,
        "failing": app.show_failing,
        "signed_out": app.show_signed_out,
        "run": app.mirror_run,
        "run_finished": app.run_finished,
    }
