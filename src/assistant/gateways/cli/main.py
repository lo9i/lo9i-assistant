"""CLI gateway entry point: the full-screen app in a terminal, the plain REPL otherwise."""

import asyncio
import sys

from assistant.core.agent import AssistantService
from assistant.core.config import settings
from assistant.gateways.cli.repl import Repl
from assistant.gateways.cli.tui.app import AssistantApp


async def _main() -> None:
    async with AssistantService.open() as service:
        session = await service.session(settings.owner_id, "cli")
        if sys.stdin.isatty() and sys.stdout.isatty():
            # No mouse capture, so a multiplexer (tmux, herdr) keeps mouse control of its panes.
            await AssistantApp(service, session).run_async(mouse=False)
        else:
            await Repl(service, session).loop()


def run() -> None:
    asyncio.run(_main())
