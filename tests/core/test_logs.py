"""The daemon's log: records written to its files, read back as entries, and followed live."""

import asyncio
import logging
from collections.abc import Iterator

import pytest

from assistant.core.logs import (
    LOG_FILES,
    LogEntry,
    LogFile,
    LogPage,
    LogQuery,
    LogQueryError,
    LogWriter,
    component_of,
    parse,
    read_page,
)


@pytest.fixture
def writer() -> Iterator[LogWriter]:
    writer = LogWriter()
    yield writer
    writer.close()


def _logger(writer: LogWriter, name: str) -> logging.Logger:
    """A logger of this test's own, whose records go only to `writer`, whatever the root logger has."""
    logger = logging.getLogger(name)
    logger.handlers, logger.propagate = [writer], False
    logger.setLevel(logging.DEBUG)
    return logger


def test_components_come_from_the_logger_names():
    assert component_of("assistant.core.mcp.process") == "mcp"
    assert component_of("assistant.core.agent.archive") == "agent"
    assert component_of("assistant.core.conversation.memory_writer") == "memory"
    assert component_of("assistant.daemon.scheduler") == "scheduler"
    assert component_of("assistant.daemon.server") == "daemon"
    assert component_of("uvicorn.error") == "other"
    assert component_of("assistant.core.mcpx") == "other"


def test_a_traceback_stays_with_its_record():
    text = (
        "Traceback before any record\n"
        "2026-10-07 10:00:00,001 INFO assistant.daemon.server: Daemon ready\n"
        "2026-10-07 10:00:01,002 ERROR assistant.core.mcp.hub: Couldn't connect\n"
        "Traceback (most recent call last):\n"
        "  ValueError: no\n"
    )
    entries = parse(text)
    assert [e.level for e in entries] == ["", "INFO", "ERROR"]
    assert entries[0].message == "Traceback before any record" and entries[0].component == "other"
    assert entries[2] == LogEntry(
        "2026-10-07 10:00:01,002",
        "ERROR",
        "assistant.core.mcp.hub",
        "mcp",
        "Couldn't connect\nTraceback (most recent call last):\n  ValueError: no",
    )


async def test_records_go_to_every_file_that_keeps_their_level(writer):
    logger = _logger(writer, "assistant.core.mcp.test_logs")
    logger.info("started notes")
    try:
        raise ValueError("boom")
    except ValueError:
        logger.exception("notes crashed")
    daemon = await read_page(LOG_FILES["daemon"], LogQuery())
    errors = await read_page(LOG_FILES["errors"], LogQuery())
    assert [e.message.splitlines()[0] for e in daemon.entries] == ["started notes", "notes crashed"]
    assert [e.level for e in errors.entries] == ["ERROR"] and "ValueError: boom" in errors.entries[0].message
    assert daemon.file.file_name == "daemon.log" and daemon.file.size > 0


async def test_a_query_picks_the_level_the_component_and_the_latest_lines(writer):
    mcp, daemon = _logger(writer, "assistant.core.mcp.test_logs"), _logger(writer, "assistant.daemon.test_logs")
    for n in range(5):
        mcp.info("mcp %s", n)
        daemon.warning("daemon %s", n)
    mcp.error("mcp failed")
    file = LOG_FILES["daemon"]
    assert [e.message for e in (await read_page(file, LogQuery(component="mcp", lines=2))).entries] == [
        "mcp 4",
        "mcp failed",
    ]
    warnings = (await read_page(file, LogQuery(level="WARNING"))).entries
    assert [e.level for e in warnings] == ["WARNING"] * 5 + ["ERROR"]


async def test_the_latest_lines_reach_into_rotated_parts(tmp_path):
    small = LogFile("small", "", logging.NOTSET, 200, 2)
    writer = LogWriter([small])
    try:
        logger = _logger(writer, "assistant.daemon.test_logs")
        for n in range(10):
            logger.info("line %s", n)
        assert small.path().with_name("small.log.1").exists()
        page = await read_page(small, LogQuery(lines=4))
        assert [e.message for e in page.entries] == ["line 6", "line 7", "line 8", "line 9"]
    finally:
        writer.close()


async def test_a_missing_file_reads_as_empty():
    page = await read_page(LOG_FILES["errors"], LogQuery())
    assert page.entries == [] and page.file.size == 0


def test_unknown_queries_are_refused():
    with pytest.raises(LogQueryError):
        LogQuery(component="nope")
    with pytest.raises(LogQueryError):
        LogQuery(level="LOUD")
    with pytest.raises(LogQueryError):
        LogQuery(lines=0)


async def test_following_starts_with_the_latest_entries_then_each_new_one(writer):
    logger = _logger(writer, "assistant.core.agent.test_logs")
    logger.info("before")
    stream = writer.follow(LOG_FILES["daemon"], LogQuery(level="INFO"))
    page = await anext(stream)
    assert isinstance(page, LogPage) and [e.message for e in page.entries] == ["before"]
    logger.debug("too quiet")
    logger.info("after")
    entry = await asyncio.wait_for(anext(stream), 1)
    assert isinstance(entry, LogEntry) and entry.message == "after" and entry.component == "agent"
    await stream.aclose()


async def test_records_from_other_threads_reach_a_follower(writer):
    logger = _logger(writer, "assistant.daemon.test_logs")
    stream = writer.follow(LOG_FILES["errors"], LogQuery())
    page = await anext(stream)
    assert isinstance(page, LogPage) and page.entries == []
    await asyncio.to_thread(logger.info, "not an error")
    await asyncio.to_thread(logger.error, "from a thread")
    entry = await asyncio.wait_for(anext(stream), 1)
    assert isinstance(entry, LogEntry) and entry.message == "from a thread"
    await stream.aclose()
