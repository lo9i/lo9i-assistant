"""Starts the daemon: opens the service, serves the API on a Unix socket and on localhost, and
supervises the channel adapters. Stops cleanly on SIGINT or SIGTERM."""

import asyncio
import contextlib
import logging
import signal
from pathlib import Path

import httpx
import uvicorn
from dotenv import load_dotenv

from assistant.core.agent import AssistantService
from assistant.core.config import settings
from assistant.core.web import browser
from assistant.daemon import launchd
from assistant.daemon.adapters import supervise
from assistant.daemon.api import create_app
from assistant.daemon.runs import RunHub
from assistant.daemon.scheduler import Scheduler
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
    if await _already_running(socket_path):
        # One daemon at a time. Under launchd this one is retried, and takes over once the other exits.
        logger.info("Another daemon is already running on %s; exiting.", socket_path)
        return
    socket_path.unlink(missing_ok=True)
    async with AssistantService.open() as service:
        app = create_app(service, RunHub(service.bus), _Startup(stop))
        servers = [_server(app, uds=str(socket_path)), _server(app, host="127.0.0.1", port=settings.daemon_port)]
        tasks = [asyncio.create_task(s.serve()) for s in servers]
        tasks.append(asyncio.create_task(supervise(TelegramAdapter(service), stop)))
        tasks.append(asyncio.create_task(supervise(Scheduler(service), stop)))
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


class _Startup:
    """Start-at-boot controls for the API. After enabling, a daemon that launchd didn't start steps
    aside so the boot-managed one takes over."""

    def __init__(self, stop: asyncio.Event) -> None:
        self._stop = stop

    def status(self):
        return launchd.status()

    async def enable(self):
        result = await launchd.enable()
        if not result.managed:
            asyncio.get_running_loop().call_later(2, self._stop.set)
        return result

    async def disable(self):
        return await launchd.disable()


async def _already_running(socket_path: Path) -> bool:
    if not socket_path.exists():
        return False
    transport = httpx.AsyncHTTPTransport(uds=str(socket_path))
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://lo9i", timeout=2) as http:
            return (await http.get("/health")).status_code == 200
    except httpx.TransportError:
        return False


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
