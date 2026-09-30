"""CLI entry point. `assistant` opens the chat, starting the daemon if it isn't running;
`assistant daemon` runs the daemon in the foreground."""

import asyncio
import sys
from pathlib import Path

from assistant.client import DaemonClient, DaemonUnavailableError, connect
from assistant.core.config import settings
from assistant.gateways.cli.history import History
from assistant.gateways.cli.repl import Repl
from assistant.gateways.cli.tui.app import AssistantApp


async def _chat() -> None:
    async with connect() as client:
        session = await client.session(settings.owner_id, "cli")
        await _open(client, session)


async def _open(client: DaemonClient, session) -> None:
    if sys.stdin.isatty() and sys.stdout.isatty():
        # No mouse capture, so a multiplexer (tmux, herdr) keeps mouse control of its panes.
        history = History(Path(settings.cli_history_path).expanduser(), settings.cli_history_limit)
        await AssistantApp(client, session, history).run_async(mouse=False)
    else:
        await Repl(client, session).loop()


def run() -> None:
    if sys.argv[1:2] == ["daemon"]:
        from assistant.daemon.server import run as run_daemon

        run_daemon()
        return
    try:
        asyncio.run(_chat())
    except DaemonUnavailableError as e:
        sys.exit(str(e))
