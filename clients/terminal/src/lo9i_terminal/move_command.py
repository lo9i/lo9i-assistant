"""`lo9i migrate <host>`: moving lo9i to another computer over SSH from a shell. The daemon does the move
(daemon/moves.py); this asks it to start, says each step as the `move` events tell it changed, and cancels the move
on Ctrl+C. A host the hosts plugin keeps is signed in to as the plugin knows it, when nothing else is given."""

import asyncio
import contextlib
import getpass
import sys
from collections.abc import Awaitable, Callable

from lo9i.client import DaemonClient, connect
from lo9i.client.daemon_client.migration import MoveRunningError, NoMoveError
from lo9i.core.agent import MigrationError, MoveStatus, MoveStep
from lo9i_terminal import i18n
from lo9i_terminal.cli import Command
from lo9i_terminal.i18n import t

_MARKS = {"running": "…", "done": "✓", "skipped": "-", "failed": "✗", "waiting": " "}


async def migrate(command: Command) -> int:
    password = (
        getpass.getpass(t("The password to sign in to {host}: ", host=command.argument)) if command.password else ""
    )
    async with connect() as client:
        i18n.use(await client.language.get())
        plugin = await _plugin(client, command)
        try:
            status = await _followed(client, lambda: _start(client, command, plugin, password))
        except (MoveRunningError, MigrationError) as e:
            sys.exit(str(e))
    print(_ended(status))
    return 0 if status.state == "done" else 1


async def _plugin(client: DaemonClient, command: Command) -> str:
    """The plugin keeping a host of that name, when nothing else says how to sign in."""
    if command.user or command.port or command.key or command.password:
        return ""
    found = next((h for h in await client.migration.saved_hosts() if h.name == command.argument), None)
    if found is None:
        return ""
    print(t("{host} as {plugin} keeps it ({address}).", host=found.name, plugin=found.plugin, address=found.address))
    return found.plugin


async def _start(client: DaemonClient, command: Command, plugin: str, password: str) -> MoveStatus:
    return await client.migration.move(
        command.argument,
        plugin=plugin,
        replace=command.force,
        user=command.user,
        port=command.port,
        key_path=command.key,
        password=password,
    )


async def _followed(client: DaemonClient, start: Callable[[], Awaitable[MoveStatus]]) -> MoveStatus:
    """Starts the move once the event stream is open, so no change is missed, and follows it to its end."""
    opened = asyncio.Event()
    shown = _Shown()
    events = client.events(on_open=opened.set)
    reading = asyncio.ensure_future(anext(events))
    await asyncio.wait([reading, asyncio.ensure_future(opened.wait())], return_when=asyncio.FIRST_COMPLETED)
    try:
        status = await start()
        shown.show(status)
        while status.state == "running":
            kind, _ = await reading
            reading = asyncio.ensure_future(anext(events))
            if kind == "move":
                status = await client.migration.move_status()
                shown.show(status)
        return status
    except asyncio.CancelledError:
        # Ctrl+C: the daemon cancels it and deletes what it copied there; one that just ended has nothing to cancel.
        with contextlib.suppress(NoMoveError):
            await client.migration.cancel_move()
        raise
    finally:
        # The stream ends with the connection, when the command ends.
        reading.cancel()


class _Shown:
    """Each step's line as it changes: a running step's line is written over in a terminal, and only once
    elsewhere."""

    def __init__(self) -> None:
        self._lines: dict[str, str] = {}
        self._over = sys.stdout.isatty()
        # A running step's line is on screen without its end of line.
        self._open = False

    def show(self, status: MoveStatus) -> None:
        for step in status.steps:
            line = _line(step)
            if step.state == "waiting" or self._lines.get(step.key) == line:
                continue
            if step.state == "running" and not self._over and step.key in self._lines:
                continue
            self._lines[step.key] = line
            self._write(line, running=step.state == "running")

    def _write(self, line: str, running: bool) -> None:
        if self._over and self._open:
            sys.stdout.write("\r\033[K")
        sys.stdout.write(line if running and self._over else line + "\n")
        sys.stdout.flush()
        self._open = running and self._over


def _line(step: MoveStep) -> str:
    return f"{_MARKS.get(step.state, ' ')} {step.label}" + (f": {step.detail}" if step.detail else "")


def _ended(status: MoveStatus) -> str:
    if status.state != "done":
        return t("The move stopped: {error}", error=status.error)
    lines = [t("lo9i runs on {host} with this computer's data.", host=status.host), "", t("To do there:")]
    return "\n".join([*lines, *(f"- {item}" for item in status.to_redo)])
