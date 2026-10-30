"""Reacts to daemon events while the app is open: memory and skills reload the panel, finished jobs and
background work, MCP servers or skills that keep failing, MCP servers whose sign-in stopped working and new plugin
updates show a notification, changes refresh an open screen that shows them (its `RELOADS_ON`, in the
background), a rename updates the title, a new language is used for what shows after it, pinning or unpinning a
skill and titling the conversation update the subtitle, runs started elsewhere in this conversation appear in the
chat live, a message written in the inbox while an update installed goes where the daemon sent it on after it, and a
conversation left with /new while its reply was running reports when it finishes."""

from collections.abc import Awaitable, Callable
from typing import Any, Protocol


class LiveApp(Protocol):
    def refresh_memory(self) -> Awaitable[None]: ...
    def reload_screen(self, kind: str) -> None: ...
    def refresh_title(self) -> Awaitable[None]: ...
    def refresh_language(self) -> Awaitable[None]: ...
    def refresh_thread(self) -> Awaitable[None]: ...
    def refresh_agents(self) -> Awaitable[None]: ...
    def refresh_plugin_updates(self) -> Awaitable[None]: ...
    def mirror_run(self, run: dict[str, Any]) -> None: ...
    def go_where_sent(self, sent: dict[str, Any]) -> Awaitable[None]: ...
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
        """The panel, and /profile."""
        await app.refresh_memory()
        app.reload_screen("memory")

    async def skills(_: dict[str, Any]) -> None:
        """The panel, and /skills and /plugins."""
        await app.refresh_memory()
        app.reload_screen("skills")

    def screen(kind: str) -> Callable[[dict[str, Any]], None]:
        return lambda _: app.reload_screen(kind)

    async def settings(_: dict[str, Any]) -> None:
        await app.refresh_language()
        await app.refresh_title()
        await app.refresh_plugin_updates()
        app.reload_screen("settings")

    async def plugins(_: dict[str, Any]) -> None:
        """A check of the repositories found something new: the title's updates and the Plugins list."""
        await app.refresh_plugin_updates()
        app.reload_screen("plugins")

    async def thread(_: dict[str, Any]) -> None:
        """The conversation's pinned skills or the agent it's handed to changed."""
        await app.refresh_thread()

    def tasks(kind: str) -> Callable[[dict[str, Any]], Awaitable[None]]:
        async def changed(_: dict[str, Any]) -> None:
            """A coding task's progress or end: the subtitle's line, and the open conversations."""
            await app.refresh_thread()
            app.reload_screen(kind)

        return changed

    async def conversations(_: dict[str, Any]) -> None:
        """A conversation was listed, titled or deleted: the subtitle's title, and /conversations."""
        await app.refresh_thread()
        app.reload_screen("conversations")

    async def ending(data: dict[str, Any]) -> None:
        """A restart or stop asked for or taken back: said, and shown in /host."""
        app.show_ending(data)
        await app.reload_host()

    def run(data: dict[str, Any]) -> None:
        """A reply started: shown live when it's in this conversation, and in the open conversations."""
        app.mirror_run(data)
        app.reload_screen("run")

    async def run_finished(data: dict[str, Any]) -> None:
        """A reply ended: what /host waits for, how full the conversation's context is now, and the open
        conversations."""
        app.run_finished(data)
        app.reload_screen("run_finished")
        await app.refresh_context()
        await app.reload_host()

    async def mcp(_: dict[str, Any]) -> None:
        """Plugins changed: an agent's command may have come or gone."""
        await app.refresh_agents()
        app.reload_screen("mcp")

    return {
        "memory": memory,
        "skills": skills,
        "integrations": screen("integrations"),
        "channels": screen("channels"),
        "clients": screen("clients"),
        "jobs": screen("jobs"),
        "conversations": conversations,
        "notifications": screen("notifications"),
        "home": screen("home"),
        "doctor": screen("doctor"),
        "prompts": screen("prompts"),
        "devices": screen("devices"),
        "mcp": mcp,
        "settings": settings,
        "plugins": plugins,
        "pinned_skills": thread,
        "handoffs": thread,
        "agent_task_progress": tasks("agent_task_progress"),
        "agent_task_reports": tasks("agent_task_reports"),
        "job": app.show_job,
        "background_ended": app.show_background_ended,
        "failing": app.show_failing,
        "signed_out": app.show_signed_out,
        "update": screen("update"),
        "ending": ending,
        "run": run,
        "run_finished": run_finished,
        "sent_on": app.go_where_sent,
    }
