"""Reacts to daemon events while the app is open: memory and skills reload the panel, finished jobs and
background work, MCP servers or skills that keep failing, MCP servers whose sign-in stopped working and new plugin
updates show a notification, integration, channel, client, job, notification feed and settings changes refresh
an open screen, a rename updates the title, pinning or unpinning a skill updates the subtitle, runs started
elsewhere in this conversation appear in the chat live, and a conversation left with /new while its reply was
running reports when it finishes."""

from collections.abc import Awaitable, Callable
from typing import Any, Protocol


class LiveApp(Protocol):
    def refresh_memory(self) -> Awaitable[None]: ...
    def reload_screen(self) -> Awaitable[None]: ...
    def refresh_title(self) -> Awaitable[None]: ...
    def refresh_thread(self) -> Awaitable[None]: ...
    def refresh_agents(self) -> Awaitable[None]: ...
    def refresh_plugin_updates(self) -> Awaitable[None]: ...
    def mirror_run(self, run: dict[str, Any]) -> None: ...
    def show_job(self, job: dict[str, Any]) -> None: ...
    def show_background_ended(self, ended: dict[str, Any]) -> None: ...
    def show_failing(self, failing: dict[str, Any]) -> None: ...
    def show_signed_out(self, signed_out: dict[str, Any]) -> None: ...

    def show_ending(self, ending: dict[str, Any]) -> None: ...
    def run_finished(self, run: dict[str, Any]) -> None: ...
    def refresh_context(self) -> Awaitable[None]: ...
    def reload_host(self) -> Awaitable[None]: ...


def handlers(app: LiveApp) -> dict[str, Callable[[dict[str, Any]], Awaitable[None] | None]]:
    async def memory(_: dict[str, Any]) -> None:
        await app.refresh_memory()

    async def screen(_: dict[str, Any]) -> None:
        await app.reload_screen()

    async def settings(_: dict[str, Any]) -> None:
        await app.refresh_title()
        await app.refresh_plugin_updates()
        await app.reload_screen()

    async def plugins(_: dict[str, Any]) -> None:
        """A check of the repositories found something new: the title's updates and the Plugins list."""
        await app.refresh_plugin_updates()
        await app.reload_screen()

    async def thread(_: dict[str, Any]) -> None:
        """The conversation's pinned skills or the agent it's handed to changed."""
        await app.refresh_thread()

    async def ending(data: dict[str, Any]) -> None:
        """A restart or stop asked for or taken back: said, and shown in /host."""
        app.show_ending(data)
        await app.reload_host()

    async def run_finished(data: dict[str, Any]) -> None:
        """A reply ended: what /host waits for, and how full the conversation's context is now."""
        app.run_finished(data)
        await app.refresh_context()
        await app.reload_host()

    async def mcp(_: dict[str, Any]) -> None:
        """Plugins changed: an agent's command may have come or gone."""
        await app.refresh_agents()
        await app.reload_screen()

    return {
        "memory": memory,
        "skills": memory,
        "integrations": screen,
        "channels": screen,
        "clients": screen,
        "jobs": screen,
        "conversations": screen,
        "notifications": screen,
        "home": screen,
        "prompts": screen,
        "devices": screen,
        "mcp": mcp,
        "settings": settings,
        "plugins": plugins,
        "pinned_skills": thread,
        "handoffs": thread,
        "agent_task_progress": thread,
        "agent_task_reports": thread,
        "job": app.show_job,
        "background_ended": app.show_background_ended,
        "failing": app.show_failing,
        "signed_out": app.show_signed_out,
        "update": screen,
        "ending": ending,
        "run": app.mirror_run,
        "run_finished": run_finished,
    }
