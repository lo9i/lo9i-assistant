"""Starts the daemon: opens the service, serves the API on a Unix socket, on localhost and, when
configured, over HTTPS for other hosts, and supervises its background tasks, including the chat
channels' processes. Stops cleanly on SIGINT or SIGTERM, and restarts or stops when asked (daemon/shutdown.py)."""

import asyncio
import logging
import os
import signal
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import httpx
from dotenv import dotenv_values, load_dotenv
from sse_starlette.sse import AppStatus

from assistant.core.agent import AssistantService
from assistant.core.config import settings
from assistant.core.internet import browser
from assistant.core.logs import LogSource, LogWriter, configure, log_sources, output_path, process_output
from assistant.daemon import https, launchd, managers, output, pages, systemd, updates
from assistant.daemon.adapters import Adapter, supervise
from assistant.daemon.api import create_app
from assistant.daemon.auth import DeviceStreams, trusted
from assistant.daemon.http_server import HttpServer, Listener
from assistant.daemon.mail_watcher import MailWatcher
from assistant.daemon.pages import create_pages_app
from assistant.daemon.queued import QueuedMessages
from assistant.daemon.runs import RunHub
from assistant.daemon.scheduler import Scheduler
from assistant.daemon.shutdown import Announce, Ending, Shutdown, exec_again, from_dotenv
from assistant.daemon.startup import Startup
from assistant.daemon.updates import Updates

logger = logging.getLogger(__name__)
# How long a stop runs before the log says what it still waits for, and again each time after.
_SLOW_STOP_SECONDS = 60
# How many of the coroutines a task waits through the log names, innermost last.
_WHERE_DEPTH = 4


async def serve(logs: Mapping[str, LogSource]) -> Ending | None:
    """Returns how the daemon ended: None when another daemon was running, STOP when stopped by a signal."""
    stop = _stop_event()
    socket_path = Path(settings.daemon_socket).expanduser()
    if await _already_running(socket_path):
        # One daemon at a time. Started at boot (launchd, systemd), this one is retried and takes over
        # once the other exits.
        logger.info("Another daemon is already running on %s; exiting.", socket_path)
        return None
    socket_path.unlink(missing_ok=True)
    async with AssistantService.open() as service:
        await service.apply_log_level()
        # Before any request, so no message lands in the home conversation it retires.
        if retired := await service.retire_home(settings.owner_id):
            logger.info("Kept the home conversation %s as an archived conversation; the inbox replaces it.", retired)
        shutdown = Shutdown(service, stop, managers.current(), _announcer(service))
        hub = RunHub(service.bus)
        streams = DeviceStreams()
        updater = _updates(service, shutdown)
        app = create_app(service, hub, Startup(stop), shutdown, logs=logs, streams=streams, updates=updater)
        servers = _listeners(app, socket_path)
        page_servers = [HttpServer(create_pages_app(service, streams), at) for at in pages.listeners()]
        tasks = [asyncio.create_task(s.serve(stop), name="http server") for s in [*servers, *page_servers]]
        background = [asyncio.create_task(_catch_up_conversations(service)), asyncio.create_task(_prune(service))]
        if https.enabled():
            background.append(asyncio.create_task(https.reload_on_renewal(servers[-1], page_servers[-1])))
        scheduler = Scheduler(service)
        tasks.append(_supervised(scheduler, stop))
        tasks.append(_supervised(MailWatcher(service, scheduler), stop))
        tasks.append(_supervised(service.mcp, stop))
        tasks.append(_supervised(service.pages, stop))
        tasks.append(_supervised(service.channels_hub, stop))
        tasks.append(_supervised(service.channel_processes, stop))
        tasks.append(_supervised(service.memory_index, stop))
        tasks.append(_supervised(service.conversation_index, stop))
        tasks.append(_supervised(service.memory_writer, stop))
        tasks.append(_supervised(service.task_ends, stop))
        tasks.append(_supervised(QueuedMessages(service, hub), stop))
        tasks.append(_supervised(service.update_checker, stop))
        tasks.append(_supervised(service.home_schedule, stop))
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
        # The daemon handles signals itself, so sse_starlette never sees one; without this, open event
        # streams would hold the servers until their grace period ends (daemon/http_server.py).
        AppStatus.should_exit = True
        await until_done(tasks)
    socket_path.unlink(missing_ok=True)
    return shutdown.ending or Ending.STOP


def _supervised(adapter: Adapter, stop: asyncio.Event) -> asyncio.Task:
    return asyncio.create_task(supervise(adapter, stop), name=adapter.name)


async def until_done(tasks: list[asyncio.Task]) -> None:
    """Waits for the daemon's tasks to end. Each minute some are still running, the log says which and where each
    waits, so a stop that hangs (a model call that never answers) says what it hangs on."""
    pending = set(tasks)
    while pending:
        _, pending = await asyncio.wait(pending, timeout=_SLOW_STOP_SECONDS)
        if pending:
            waiting = "; ".join(sorted(f"{t.get_name()} at {_where(t)}" for t in pending))
            logger.warning("Still stopping: waiting for %s", waiting)


def _where(task: asyncio.Task) -> str:
    """Where the task waits: the last coroutines it awaits through, innermost last, each with its line."""
    frames = []
    coro: Any = task.get_coro()
    while coro is not None and (frame := getattr(coro, "cr_frame", None) or getattr(coro, "ag_frame", None)):
        frames.append(f"{frame.f_code.co_name} ({Path(frame.f_code.co_filename).name}:{frame.f_lineno})")
        coro = getattr(coro, "cr_await", None) or getattr(coro, "ag_await", None)
    return " → ".join(frames[-_WHERE_DEPTH:]) or "an unknown place"


def _announcer(service: AssistantService) -> Announce:
    """Tells every app a restart or stop is coming (an `ending` event)."""
    return lambda ending, waiting, taken_back: service.bus.publish(
        "ending", ending=ending.value, waiting_for_runs=waiting, taken_back=taken_back
    )


def _updates(service: AssistantService, shutdown: Shutdown) -> Updates:
    root = updates.repository_root()
    return Updates(
        root,
        updates.default_steps(root),
        restart=lambda: shutdown.request(Ending.RESTART, "an update"),
        announce=lambda: service.bus.publish("update"),
    )


def _listeners(app, socket_path: Path) -> list[HttpServer]:
    """The Unix socket, localhost, and HTTPS when configured (last). Only the Unix socket is
    trusted; network requests need a paired device (daemon/auth.py)."""
    servers = [
        HttpServer(trusted(app), Listener(socket=str(socket_path))),
        HttpServer(app, Listener(host="127.0.0.1", port=settings.daemon_port)),
    ]
    if https.enabled():
        servers.append(HttpServer(app, https.listener(settings.https_port)))
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
    those listed before channels were and the summaries of those summarized before summaries were kept
    apart, and adds messages not yet searchable to the search index (a catch-up; after it, all of this
    happens as conversations go)."""
    try:
        added = await service.index_conversations(settings.owner_id)
        filled = await service.fill_channels(settings.owner_id)
        summarized = await service.fill_summaries(settings.owner_id)
        searchable = await service.index_messages(settings.owner_id)
    except Exception:
        logger.exception("Couldn't catch up on earlier conversations")
        return
    if added or filled or summarized or searchable:
        logger.info(
            "Added %s earlier conversations to the list, recorded channels for %s and summaries for %s, and made"
            " %s messages searchable.",
            added,
            filled,
            summarized,
            searchable,
        )


async def _catch_up_conversations(service: AssistantService) -> None:
    """The conversations' catch-up, titling last: it waits on the worker model, which may not answer."""
    await _index_conversations(service)
    await _title_untitled(service)


async def _title_untitled(service: AssistantService) -> None:
    """Titles the conversations without a title or tags (core/agent/titles.py)."""
    try:
        if titled := await service.title_untitled(settings.owner_id):
            logger.info("Titled %s earlier conversations.", titled)
    except Exception:
        logger.exception("Couldn't title earlier conversations")


async def _already_running(socket_path: Path) -> bool:
    if not socket_path.exists():
        return False
    transport = httpx.AsyncHTTPTransport(uds=str(socket_path))
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://lo9i", timeout=2) as http:
            return (await http.get("/health")).status_code == 200
    except httpx.TransportError:
        return False


def _stop_event() -> asyncio.Event:
    stop = asyncio.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        asyncio.get_running_loop().add_signal_handler(sig, _stopped_by, sig, stop)
    return stop


def _stopped_by(sig: signal.Signals, stop: asyncio.Event) -> None:
    """A signal stops the daemon at once; the log says which, since a stop from the apps ends the same way."""
    logger.info("Stopping: %s received (from a service manager, a script or Ctrl+C).", sig.name)
    stop.set()


def run() -> None:
    moved = launchd.move_legacy_output()
    rotated = output.rotate(output_path())
    # Settings read .env themselves, but the model and tracing SDKs read their keys from the
    # environment, and the daemon may be started from a shell that doesn't have them.
    # A restart re-launches this process with its environment, so the keys .env added are noted and dropped
    # before it (exec_again): the new daemon reads .env afresh, and a line removed from it is gone.
    from_dotenv.update(key for key in dotenv_values(".env") if key not in os.environ)
    load_dotenv(".env", override=False)
    writer = LogWriter()
    configure(writer)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    if moved:
        logger.info(
            "Sending output to %s: the LaunchDaemon sends it to %s until start at boot is turned off and on.",
            output_path(),
            launchd.LEGACY_OUTPUT,
        )
    if rotated:
        logger.info("The output file was full: the output before is in %s.", output.kept(output_path()))
    logs = log_sources(writer, process_output(systemd.SERVICE))
    end(asyncio.run(serve(logs)))


def end(ending: Ending | None) -> None:
    """Restarts in place, or exits: cleanly when stopped, so launchd leaves it stopped (launchd.py)."""
    if ending is Ending.RESTART:
        logger.info("Restarting the daemon.")
        exec_again()
    if ending is None:
        # Not a clean stop, so launchd and systemd try again and this one takes over once the other exits.
        sys.exit(os.EX_TEMPFAIL)
    logger.info("The daemon stopped.")
