"""The session helper: opens links and apps for the plugins that ask, refuses what isn't a link or an app, links the
session's ssh agent, says its code's version and quits when asked; and its LaunchAgent, installed and kept current."""

import asyncio
import plistlib
import shutil
import sys
import tempfile
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from assistant.core import login_session
from assistant.daemon import session_agent
from assistant.daemon.session_agent import SessionAgent
from assistant.session.helper import SessionHelper
from assistant.session.protocol import HelperUnavailableError, ask, code_digest, open_arguments


@pytest.fixture
def folder():
    # Under /tmp: macOS limits socket paths to 104 characters, and pytest's tmp_path is longer.
    path = Path(tempfile.mkdtemp(prefix="lo9i-"))
    yield path
    shutil.rmtree(path, ignore_errors=True)


class Opened:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.failure = ""

    async def __call__(self, arguments: list[str]) -> str:
        self.calls.append(arguments)
        return self.failure


@pytest.fixture
async def helper(folder) -> AsyncIterator[tuple[Path, Opened, asyncio.Task]]:
    opened, stop = Opened(), asyncio.Event()
    serving = SessionHelper(folder / "s.sock", folder / "agent.sock", "/tmp/launchd-agent/Listeners", opened)
    task = asyncio.create_task(serving.serve(stop))
    while not (folder / "s.sock").exists():
        await asyncio.sleep(0.01)
    yield folder / "s.sock", opened, task
    stop.set()
    await task


async def test_it_opens_a_link_with_an_app_on_the_screen(helper):
    socket, opened, _ = helper
    assert await ask(socket, {"op": "open", "url": "tel:+5491112345678"}) == {"ok": True}
    assert await ask(socket, {"op": "open", "url": "tel:123", "app": "Phone"}) == {"ok": True}
    assert opened.calls == [["tel:+5491112345678"], ["-a", "Phone", "tel:123"]]
    opened.failure = "No application knows how to open it."
    assert await ask(socket, {"op": "open", "url": "zzz:x"}) == {"error": "No application knows how to open it."}


@pytest.mark.parametrize(
    ("url", "app"),
    [("file:///Users/me/run.command", ""), ("/Applications/Calculator.app", ""), ("-a", ""), ("", "-n"), ("", "")],
)
def test_only_links_and_apps_are_opened(url, app):
    with pytest.raises(ValueError):
        open_arguments(url, app)


async def test_what_it_refuses_comes_back_as_an_error(helper):
    socket, opened, _ = helper
    assert "isn't a link" in (await ask(socket, {"op": "open", "url": "file:///etc/passwd"}))["error"]
    assert "Unknown request" in (await ask(socket, {"op": "rm"}))["error"]
    assert opened.calls == []


async def test_it_links_the_sessions_ssh_agent_while_it_runs(helper, folder):
    assert (folder / "agent.sock").readlink() == Path("/tmp/launchd-agent/Listeners")
    assert (folder / "s.sock").stat().st_mode & 0o777 == 0o600


async def test_it_says_its_version_and_quits_when_asked(helper, folder):
    socket, _, task = helper
    assert await ask(socket, {"op": "version"}) == {"version": code_digest()}
    assert await ask(socket, {"op": "quit"}) == {"ok": True}
    await asyncio.wait_for(task, 2)
    assert not socket.exists() and not (folder / "agent.sock").is_symlink()
    with pytest.raises(HelperUnavailableError):
        await ask(socket, {"op": "version"})


def test_the_agent_runs_this_python_in_a_session_with_a_screen():
    plist = plistlib.loads(session_agent.agent_plist())
    assert plist["ProgramArguments"] == [sys.executable, "-m", "assistant.session"]
    assert plist["LimitLoadToSessionType"] == "Aqua" and plist["KeepAlive"] is True


class Launchctl:
    def __init__(self, bootstrap: int = 0) -> None:
        self.calls: list[list[str]] = []
        self._bootstrap = bootstrap

    async def __call__(self, arguments: list[str]) -> tuple[int, str]:
        self.calls.append(arguments)
        return (self._bootstrap if arguments[0] == "bootstrap" else 0), "Domain does not support specified action"


async def test_installing_puts_the_plist_in_place_and_loads_it_into_the_session(folder):
    launchctl = Launchctl()
    agent = SessionAgent(folder / "LaunchAgents", launchctl, uid=501)
    await agent.install()
    plist = folder / "LaunchAgents" / f"{session_agent.LABEL}.plist"
    assert plist.read_bytes() == session_agent.agent_plist()
    assert launchctl.calls == [
        ["bootout", f"gui/501/{session_agent.LABEL}"],
        ["bootstrap", "gui/501", str(plist)],
    ]
    await agent.remove()
    assert not plist.exists()


async def test_installed_while_nobody_is_logged_in_it_waits_for_the_next_login(folder, caplog):
    agent = SessionAgent(folder / "LaunchAgents", Launchctl(bootstrap=125), uid=501)
    with caplog.at_level("INFO"):
        await agent.install()
    assert (folder / "LaunchAgents" / f"{session_agent.LABEL}.plist").exists()
    assert "starts at the next login" in caplog.text


async def test_at_start_a_missing_agent_is_installed_and_a_current_one_left(folder, monkeypatch):
    monkeypatch.setattr(login_session, "socket_path", lambda: folder / "none.sock")
    launchctl = Launchctl()
    agent = SessionAgent(folder / "LaunchAgents", launchctl, uid=501)
    await agent.ensure()
    assert [c[0] for c in launchctl.calls] == ["bootout", "bootstrap"]
    await agent.ensure()  # Up to date, and no helper answers: nothing to do.
    assert len(launchctl.calls) == 2


async def test_at_start_a_helper_running_older_code_is_asked_to_quit(helper, folder, monkeypatch):
    socket, _, task = helper
    monkeypatch.setattr(login_session, "socket_path", lambda: socket)
    monkeypatch.setattr(session_agent, "code_digest", lambda: "newer")
    agent = SessionAgent(folder / "LaunchAgents", Launchctl(), uid=501)
    await agent.install()
    await agent.ensure()
    await asyncio.wait_for(task, 2)
