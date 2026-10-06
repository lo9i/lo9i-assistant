"""Starts the daemon: opens the service, serves the API on a Unix socket, on localhost and, when
configured, over HTTPS for other hosts, and supervises its background tasks, including the chat
channels' processes. Stops cleanly on SIGINT or SIGTERM, and starts again when asked to restart."""

import asyncio
import contextlib
import logging
import signal
from pathlib import Path

import httpx
import uvicorn
from dotenv import load_dotenv
from sse_starlette.sse import AppStatus

from assistant.core.agent import AssistantService
from assistant.core.config import settings
from assistant.core.internet import browser
from assistant.daemon import https, pages
from assistant.daemon.adapters import supervise
from assistant.daemon.api import create_app
from assistant.daemon.auth import trusted
from assistant.daemon.mail_watcher import MailWatcher
from assistant.daemon.pages import create_pages_app
from assistant.daemon.restart import Restart, exec_again
from assistant.daemon.runs import RunHub
from assistant.daemon.scheduler import Scheduler
from assistant.daemon.startup import Startup

logger = logging.getLogger(__name__)


class _Server(uvicorn.Server):
    """Two servers share one process, so signals are handled once, by the daemon."""

    @contextlib.contextmanager
    def capture_signals(self):
        yield


async def serve() -> bool:
    """Returns whether the daemon stopped to restart."""
    stop = _stop_event()
    socket_path = Path(settings.daemon_socket).expanduser()
    if await _already_running(socket_path):
        # One daemon at a time. Started at boot (launchd, systemd), this one is retried and takes over
        # once the other exits.
        logger.info("Another daemon is already running on %s; exiting.", socket_path)
        return False
    socket_path.unlink(missing_ok=True)
    async with AssistantService.open() as service:
        # Before any request, so no channel message lands in a conversation it's leaving.
        if moved := await service.channels_to_home(settings.owner_id):
            logger.info("Moved %s chat channels to the home conversation.", moved)
        restart = Restart(service, stop)
        app = create_app(service, RunHub(service.bus), Startup(stop), restart)
        servers = _listeners(app, socket_path)
        page_servers = [_server(create_pages_app(service), **bind) for bind in pages.ports()]
        tasks = [asyncio.create_task(s.serve()) for s in [*servers, *page_servers]]
        background = [asyncio.create_task(_index_conversations(service)), asyncio.create_task(_prune(service))]
        if https.enabled():
            background.append(asyncio.create_task(https.reload_on_renewal(servers[-1], page_servers[-1])))
        scheduler = Scheduler(service)
        tasks.append(asyncio.create_task(supervise(scheduler, stop)))
        tasks.append(asyncio.create_task(supervise(MailWatcher(service, scheduler), stop)))
        tasks.append(asyncio.create_task(supervise(service.mcp, stop)))
        tasks.append(asyncio.create_task(supervise(service.pages, stop)))
        tasks.append(asyncio.create_task(supervise(service.channels_hub, stop)))
        tasks.append(asyncio.create_task(supervise(service.channel_processes, stop)))
        tasks.append(asyncio.create_task(supervise(service.memory_index, stop)))
        tasks.append(asyncio.create_task(supervise(service.memory_writer, stop)))
        tasks.append(asyncio.create_task(supervise(service.update_checker, stop)))
        # Downloads once in the background; until then pages are read without rendering.
        install = asyncio.create_task(browser.install_browser()) if settings.web_render else None
        logger.info("Daemon ready on %s and http://127.0.0.1:%s", socket_path, settings.daemon_port)
        if https.enabled():
            logger.info("Serving HTTPS for %s on %s:%s", settings.https_host, settings.https_bind, settings.https_port)
        await stop.wait()
        if install is not None:
            install.cancel()
        for task in background:
            task.cancel()
        # The daemon handles signals itself (`_Server`), so sse_starlette never sees one; without
        # this, open event streams keep the servers waiting for them to end.
        AppStatus.should_exit = True
        for server in [*servers, *page_servers]:
            server.should_exit = True
        await asyncio.gather(*tasks, return_exceptions=True)
    socket_path.unlink(missing_ok=True)
    return restart.requested


def _listeners(app, socket_path: Path) -> list["_Server"]:
    """The Unix socket, localhost, and HTTPS when configured (last). Only the Unix socket is
    trusted; network requests need a paired device (daemon/auth.py)."""
    servers = [_server(trusted(app), uds=str(socket_path)), _server(app, host="127.0.0.1", port=settings.daemon_port)]
    if https.enabled():
        servers.append(_server(app, **https.bind()))
    return servers


async def _prune(service: AssistantService) -> None:
    """Prunes the checkpoints of conversations saved before runs pruned their own (a catch-up)."""
    try:
        if pruned := await service.prune_checkpoints():
            logger.info("Pruned %s old checkpoints.", pruned)
    except Exception:
        logger.exception("Couldn't prune old checkpoints")


async def _index_conversations(service: AssistantService) -> None:
    """Lists conversations saved before the conversation list existed, records the channels of
    those listed before channels were, titles those without a title from the model, and adds
    messages not yet searchable to the search index (a catch-up; after it, all of this happens as
    conversations go)."""
    try:
        added = await service.index_conversations(settings.owner_id)
        filled = await service.fill_channels(settings.owner_id)
        titled = await service.title_untitled(settings.owner_id)
        searchable = await service.index_messages(settings.owner_id)
    except Exception:
        logger.exception("Couldn't catch up on earlier conversations")
        return
    if added or filled or titled or searchable:
        logger.info(
            "Added %s earlier conversations to the list, recorded channels for %s, titled %s and made %s "
            "messages searchable.",
            added,
            filled,
            titled,
            searchable,
        )


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
    if asyncio.run(serve()):
        logger.info("Restarting the daemon.")
        exec_again()
