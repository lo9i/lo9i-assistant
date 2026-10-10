"""The daemon's process output on the Logs page: the output file, followed as another writer appends to
it, and the systemd journal read with journalctl."""

import asyncio
import json
import os
import sys
from pathlib import Path

import pytest

from assistant.core.logs import Journal, LogEntry, LogPage, LogQuery, OutputFile, output_path, process_output
from assistant.core.logs.output import stderr_is_journal


def _append(path: Path, text: str) -> None:
    with path.open("a") as out:
        out.write(text)


async def test_a_page_has_the_latest_lines_of_the_output():
    path = output_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    _append(path, "".join(f"line {n}\n" for n in range(5)) + "Traceback (most recent call last):\n")
    page = await OutputFile(path).page(LogQuery(lines=3))
    assert [e.message for e in page.entries] == ["line 3", "line 4", "Traceback (most recent call last):"]
    assert {e.level for e in page.entries} == {""} and page.file.name == "output"
    assert page.file.file_name == "output.log" and page.file.size


async def test_no_output_yet_reads_as_empty():
    page = await OutputFile(output_path()).page(LogQuery())
    assert page.entries == [] and page.file.size == 0


async def test_following_the_output_sees_what_another_writer_appends():
    path = output_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    _append(path, "before\n")
    async with asyncio.timeout(10):
        stream = OutputFile(path).follow(LogQuery())
        page = await anext(stream)
        assert isinstance(page, LogPage) and [e.message for e in page.entries] == ["before"]
        # Another process holds the file open and appends, as the daemon's stderr does.
        writer = await asyncio.create_subprocess_exec(sys.executable, "-c", f"open({str(path)!r}, 'a').write('half')")
        await writer.wait()
        _append(path, " a line\nnext\n")
        first, second = await anext(stream), await anext(stream)
        assert isinstance(first, LogEntry) and first.message == "half a line"
        assert isinstance(second, LogEntry) and second.message == "next"
        await stream.aclose()


async def test_following_output_that_was_cut_short_reads_it_from_the_start():
    path = output_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    _append(path, "a long line from before\n")
    async with asyncio.timeout(10):
        stream = OutputFile(path).follow(LogQuery())
        await anext(stream)
        path.write_text("new\n")
        entry = await anext(stream)
        assert isinstance(entry, LogEntry) and entry.message == "new"
        await stream.aclose()


async def test_closing_a_followed_output_stops_watching_at_once():
    stream = OutputFile(output_path()).follow(LogQuery())
    page = await anext(stream)
    assert isinstance(page, LogPage) and page.entries == []
    async with asyncio.timeout(1):
        await stream.aclose()


def test_the_journal_is_read_only_when_systemd_connected_stderr_to_it(monkeypatch):
    stat = os.fstat(2)
    monkeypatch.setenv("JOURNAL_STREAM", f"{stat.st_dev}:{stat.st_ino}")
    assert stderr_is_journal() and isinstance(process_output("lo9i-assistant"), Journal)
    # Inherited from a service, by a process whose stderr is something else.
    monkeypatch.setenv("JOURNAL_STREAM", f"{stat.st_dev}:{stat.st_ino + 1}")
    assert not stderr_is_journal() and isinstance(process_output("lo9i-assistant"), OutputFile)
    monkeypatch.delenv("JOURNAL_STREAM")
    assert isinstance(process_output("lo9i-assistant"), OutputFile)


def _journal_entry(cursor: str, message: object, priority: str = "6", identifier: str = "python") -> dict:
    return {
        "__CURSOR": cursor,
        "__REALTIME_TIMESTAMP": "1791000000123456",
        "PRIORITY": priority,
        "SYSLOG_IDENTIFIER": identifier,
        "MESSAGE": message,
    }


_FAKE_JOURNALCTL = """
import json, sys, time
args = sys.argv[1:]
with open(sys.argv[0] + ".calls", "a") as calls:
    calls.write(json.dumps(args) + "\\n")
entries = json.load(open(sys.argv[0] + ".json"))
if "--follow" in args:
    print(json.dumps(entries["new"]), flush=True)
    time.sleep(60)
else:
    for entry in entries["old"]:
        print(json.dumps(entry))
"""


@pytest.fixture
def journalctl(tmp_path) -> Path:
    """A journalctl that prints `old` for a page, and `new` when following, then waits."""
    script = tmp_path / "journalctl"
    script.write_text(_FAKE_JOURNALCTL)
    old = [
        _journal_entry("c1", "Started lo9i assistant daemon.", "6", "systemd"),
        _journal_entry("c2", "Traceback (most recent call last):"),
        _journal_entry("c3", list(b"bad \xff byte"), "3"),
    ]
    script.with_suffix(".json").write_text(json.dumps({"old": old, "new": _journal_entry("c4", "fresh", "4")}))
    return script


def _calls(script: Path) -> list[list[str]]:
    return [json.loads(line) for line in script.with_suffix(".calls").read_text().splitlines()]


async def test_the_journal_page_keeps_each_entrys_time_priority_and_program(journalctl):
    journal = Journal("lo9i-assistant", (sys.executable, str(journalctl)))
    page = await journal.page(LogQuery(lines=2))
    assert [(e.level, e.logger, e.message) for e in page.entries] == [
        ("INFO", "python", "Traceback (most recent call last):"),
        ("ERROR", "python", "bad � byte"),
    ]
    assert page.entries[0].time.endswith(",123") and page.file.size is None
    assert "--user-unit=lo9i-assistant" in _calls(journalctl)[0]
    errors = await journal.page(LogQuery(level="ERROR"))
    assert [e.message for e in errors.entries] == ["bad � byte"]


async def test_following_the_journal_goes_on_after_the_last_entry_read(journalctl):
    journal = Journal("lo9i-assistant", (sys.executable, str(journalctl)))
    async with asyncio.timeout(10):
        stream = journal.follow(LogQuery())
        page = await anext(stream)
        assert isinstance(page, LogPage) and len(page.entries) == 3
        entry = await anext(stream)
        assert isinstance(entry, LogEntry) and (entry.level, entry.message) == ("WARNING", "fresh")
        await stream.aclose()
    follow = _calls(journalctl)[-1]
    assert "--follow" in follow and "--after-cursor=c3" in follow


async def test_a_journal_that_cant_be_read_says_why(tmp_path):
    page = await Journal("lo9i-assistant", (str(tmp_path / "missing"),)).page(LogQuery())
    assert [e.level for e in page.entries] == ["ERROR"] and "isn't installed" in page.entries[0].message
    failing = Journal("lo9i-assistant", (sys.executable, "-c", "import sys; sys.exit('No journal files')"))
    page = await failing.page(LogQuery())
    assert "No journal files" in page.entries[0].message
