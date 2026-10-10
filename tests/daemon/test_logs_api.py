"""The log routes through DaemonClient."""

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator, Iterator

import httpx
import pytest
import uvicorn

from assistant.client.daemon_client import DaemonClient
from assistant.core.logs import (
    LogEntry,
    LogLevelError,
    LogPage,
    LogQueryError,
    LogWriter,
    OutputFile,
    log_sources,
    output_path,
)
from assistant.daemon.api import create_app
from assistant.daemon.auth import trusted
from assistant.daemon.runs import RunHub
from assistant.protocol import CLIENT_HEADER


@pytest.fixture
def writer() -> Iterator[LogWriter]:
    writer = LogWriter()
    yield writer
    writer.close()


@pytest.fixture
def logger(writer) -> Iterator[logging.Logger]:
    logger = logging.getLogger("assistant.core.mcp.process")
    logger.handlers, logger.propagate = [writer], False
    logger.setLevel(logging.DEBUG)
    yield logger
    logger.handlers, logger.propagate = [], True
    logger.setLevel(logging.NOTSET)


@pytest.fixture
async def app(service, writer):
    return create_app(service, RunHub(), logs=log_sources(writer, OutputFile(output_path())))


@pytest.fixture
async def client(app) -> AsyncIterator[DaemonClient]:
    transport = httpx.ASGITransport(app=trusted(app))
    async with httpx.AsyncClient(transport=transport, base_url="http://lo9i", headers={CLIENT_HEADER: "t"}) as http:
        yield DaemonClient(http)


async def test_the_options_list_the_files_levels_and_components(client):
    options = await client.logs.options()
    assert [f.file_name for f in options.files] == ["daemon.log", "errors.log", "output.log"]
    assert options.levels == ["DEBUG", "INFO", "WARNING", "ERROR"]
    assert {"agent", "mcp", "channels", "scheduler", "daemon", "other"} <= set(options.components)


async def test_a_page_has_the_latest_matching_entries(client, logger):
    logger.info("connected")
    logger.warning("slow")
    logger.error("crashed")
    page = await client.logs.page("daemon", level="WARNING", component="mcp", lines=50)
    assert [(e.level, e.message) for e in page.entries] == [("WARNING", "slow"), ("ERROR", "crashed")]
    assert [e.message for e in (await client.logs.page("errors")).entries] == ["crashed"]
    assert (await client.logs.page("daemon", component="agent")).entries == []


async def test_the_output_reads_like_a_log(client):
    output_path().write_text("Traceback (most recent call last):\n  ImportError: no\n")
    page = await client.logs.page("output")
    assert [e.message for e in page.entries] == ["Traceback (most recent call last):", "  ImportError: no"]
    assert page.file.name == "output"


async def test_the_level_the_daemon_records_at_changes_at_once(client):
    own = logging.getLogger("assistant")
    saved = own.level, logging.getLogger().level
    try:
        assert await client.logs.level() == "INFO"
        assert await client.logs.set_level("DEBUG") == "DEBUG"
        assert own.isEnabledFor(logging.DEBUG) and await client.logs.level() == "DEBUG"
        with pytest.raises(LogLevelError, match="Unknown level"):
            await client.logs.set_level("LOUD")
    finally:
        own.setLevel(saved[0])
        logging.getLogger().setLevel(saved[1])


async def test_unknown_files_and_components_are_refused(client):
    with pytest.raises(LogQueryError, match="No log named"):
        await client.logs.page("secrets")
    with pytest.raises(LogQueryError, match="Unknown component"):
        await client.logs.page("daemon", component="nope")


async def test_following_a_log_sends_its_page_then_new_entries(app, logger):
    """Over a real socket: the in-process transport doesn't stream."""
    logger.info("before")
    # asyncio.timeout, not wait_for: the stream must be read from this task, which closes it.
    async with (
        _serving(app) as client,
        asyncio.timeout(5),
        contextlib.aclosing(client.logs.follow("daemon", component="mcp")) as stream,
    ):
        page = await anext(stream)
        assert isinstance(page, LogPage) and [e.message for e in page.entries] == ["before"]
        logger.info("after")
        entry = await anext(stream)
        assert isinstance(entry, LogEntry) and entry.message == "after"


@contextlib.asynccontextmanager
async def _serving(app) -> AsyncIterator[DaemonClient]:
    """As the Unix socket would (trusted), on a TCP port: a socket path under pytest's temporary
    folder is longer than macOS allows."""
    config = uvicorn.Config(trusted(app), host="127.0.0.1", port=0, log_level="warning", lifespan="off")
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve())
    while not server.started:
        await asyncio.sleep(0.01)
    port = server.servers[0].sockets[0].getsockname()[1]
    try:
        async with httpx.AsyncClient(
            base_url=f"http://127.0.0.1:{port}", headers={CLIENT_HEADER: "t"}, timeout=10
        ) as http:
            yield DaemonClient(http)
    finally:
        server.should_exit = True
        await task
