"""CLI entry point. `assistant` opens the chat, starting the daemon if it isn't running;
`assistant daemon` runs the daemon in the foreground."""

import asyncio
import sys

from assistant.client import DaemonClient, connect
from assistant.core.config import settings
from assistant.gateways.cli.repl import Repl
from assistant.gateways.cli.tui.app import AssistantApp


async def _chat() -> None:
    async with connect() as client:
        session = await client.session(settings.owner_id, "cli")
        await _open(client, session)


async def _open(client: DaemonClient, session) -> None:
    if sys.stdin.isatty() and sys.stdout.isatty():
        # No mouse capture, so a multiplexer (tmux, herdr) keeps mouse control of its panes.
        await AssistantApp(client, session).run_async(mouse=False)
    else:
        await Repl(client, session).loop()


def run() -> None:
    if sys.argv[1:2] == ["daemon"]:
        from assistant.daemon.server import run as run_daemon

        run_daemon()
        return
    asyncio.run(_chat())
