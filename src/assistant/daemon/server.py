"""Starts the daemon: opens the service, serves the API on a Unix socket and on localhost, and
supervises the channel adapters. Stops cleanly on SIGINT or SIGTERM."""

import asyncio
import contextlib
import logging
import signal
from pathlib import Path

import uvicorn
from dotenv import load_dotenv

from assistant.core.agent import AssistantService
from assistant.core.config import settings
from assistant.daemon.adapters import supervise
from assistant.daemon.api import create_app
from assistant.daemon.runs import RunHub
from assistant.core.web import browser
from assistant.gateways.telegram.bot import TelegramAdapter

logger = logging.getLogger(__name__)


class _Server(uvicorn.Server):
    """Two servers share one process, so signals are handled once, by the daemon."""

    @contextlib.contextmanager
    def capture_signals(self):
        yield


async def serve() -> None:
    stop = _stop_event()
    socket_path = Path(settings.daemon_socket).expanduser()
    socket_path.unlink(missing_ok=True)
    async with AssistantService.open() as service:
        app = create_app(service, RunHub())
        servers = [_server(app, uds=str(socket_path)), _server(app, host="127.0.0.1", port=settings.daemon_port)]
        tasks = [asyncio.create_task(s.serve()) for s in servers]
        tasks.append(asyncio.create_task(supervise(TelegramAdapter(service), stop)))
        # Downloads once in the background; until then pages are read without rendering.
        install = asyncio.create_task(browser.install_browser()) if settings.web_render else None
        logger.info("Daemon ready on %s and http://127.0.0.1:%s", socket_path, settings.daemon_port)
        await stop.wait()
        if install is not None:
            install.cancel()
        for server in servers:
            server.should_exit = True
        await asyncio.gather(*tasks, return_exceptions=True)
    socket_path.unlink(missing_ok=True)


def _server(app, **bind) -> _Server:
    return _Server(uvicorn.Config(app, log_level="warning", lifespan="off", **bind))


def _stop_event() -> asyncio.Event:
    stop = asyncio.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        asyncio.get_running_loop().add_signal_handler(sig, stop.set)
    return stop


def run() -> None:
    # Settings read .env themselves, but the model and tracing SDKs read their keys from the
    # environment, and the daemon may be started from a shell that doesn't have them.
    load_dotenv(".env", override=False)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    asyncio.run(serve())
