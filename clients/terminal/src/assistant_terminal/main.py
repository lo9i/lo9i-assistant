"""CLI entry point. `assistant` opens the chat, starting the daemon if it isn't running;
`assistant daemon` runs the daemon in the foreground; `assistant daemon restart` restarts the running one
once no run is in progress."""

import asyncio
import sys
from pathlib import Path

from assistant.client import DaemonClient, DaemonUnavailableError, connect
from assistant.core.agent import Session
from assistant.core.config import settings
from assistant_terminal.history import History
from assistant_terminal.preferences import Preferences
from assistant_terminal.repl import Repl
from assistant_terminal.tui.app import AssistantApp


async def _chat() -> None:
    async with connect() as client:
        # Every terminal opens on the inbox, which routes each message to its conversation; /new starts one,
        # /conversations opens one.
        session = Session(settings.owner_id, "cli", await client.inbox_thread(settings.owner_id))
        await _open(client, session)


async def _open(client: DaemonClient, session: Session) -> None:
    if sys.stdin.isatty() and sys.stdout.isatty():
        history = History(Path(settings.cli_history_path).expanduser(), settings.cli_history_limit)
        preferences = Preferences(Path(settings.cli_preferences_path).expanduser())
        await AssistantApp(client, session, history, preferences).run_async(mouse=preferences.mouse)
    else:
        await Repl(client, session).loop()


async def _restart() -> None:
    async with connect() as client:
        waiting = (await client.system.restart()).waiting_for_runs
    print(f"The daemon restarts once the {waiting} runs in progress end." if waiting else "The daemon restarts now.")


def run() -> None:
    if sys.argv[1:] == ["daemon"]:
        from assistant.daemon.server import run as run_daemon

        run_daemon()
        return
    try:
        asyncio.run(_restart() if sys.argv[1:] == ["daemon", "restart"] else _chat())
    except DaemonUnavailableError as e:
        sys.exit(str(e))
