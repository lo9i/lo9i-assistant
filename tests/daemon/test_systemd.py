"""Start at boot on Linux: the systemd user service, what status reads, and the commands that turn it
on and off. systemctl and loginctl are faked; nothing is installed."""

import asyncio
import os
import sys
from pathlib import Path

import pytest

from assistant.daemon import startup, systemd
from assistant.protocol import StartupError, StartupStatus


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(systemd, "_LINGER_DIR", tmp_path / "linger")
    monkeypatch.setattr(systemd.getpass, "getuser", lambda: "lo9i")
    return tmp_path


@pytest.fixture
def commands(home: Path, monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, ...]]:
    """Runs systemctl and loginctl as a fake: enabling links the unit, lingering creates its file."""
    ran: list[tuple[str, ...]] = []

    async def run(*command: str) -> tuple[int, str]:
        ran.append(command)
        if command[2:4] == ("enable", "--now"):
            systemd._wants_link().parent.mkdir(parents=True, exist_ok=True)
            systemd._wants_link().touch()
        if command[2:3] == ("disable",):
            systemd._wants_link().unlink()
        return 0, ""

    monkeypatch.setattr(systemd, "_run", run)
    return ran


def test_the_unit_runs_this_python_from_here_and_marks_the_daemon_as_managed():
    unit = systemd.unit()
    assert f'ExecStart="{sys.executable}" -m assistant.daemon' in unit
    assert f"Environment={systemd.MANAGED_ENV}=1" in unit and "Restart=always" in unit
    assert "WantedBy=default.target" in unit


async def test_enable_installs_starts_and_asks_for_lingering(home, commands):
    status = await systemd.enable()
    assert systemd.unit_path().read_text() == systemd.unit()
    assert commands == [
        ("systemctl", "--user", "daemon-reload"),
        ("systemctl", "--user", "enable", "--now", "lo9i-assistant"),
        ("loginctl", "enable-linger", "lo9i"),
    ]
    assert status.enabled and status.platform == "linux" and not status.starts_without_login


async def test_lingering_already_on_isnt_asked_again(home, commands):
    (home / "linger").mkdir()
    (home / "linger" / "lo9i").touch()
    status = await systemd.enable()
    assert ("loginctl", "enable-linger", "lo9i") not in commands and status.starts_without_login


async def test_disable_removes_the_service(home, commands):
    await systemd.enable()
    status = await systemd.disable()
    assert not systemd.unit_path().exists() and not status.enabled
    assert ("systemctl", "--user", "disable", "lo9i-assistant") in commands


async def test_a_failing_systemctl_is_reported(home, monkeypatch):
    async def run(*command: str) -> tuple[int, str]:
        return 1, "Failed to connect to bus"

    monkeypatch.setattr(systemd, "_run", run)
    with pytest.raises(StartupError, match="Failed to connect to bus"):
        await systemd.enable()


async def test_other_systems_say_start_at_boot_isnt_available(monkeypatch):
    monkeypatch.setattr(startup.sys, "platform", "win32")
    controls = startup.Startup(asyncio.Event())
    assert controls.status().platform == "unsupported"
    with pytest.raises(StartupError, match="macOS and on Linux"):
        await controls.enable()


async def test_stopping_asks_systemd_to_stop_the_service_without_waiting(commands):
    stop = asyncio.Event()
    await systemd.Service().stop(stop)
    assert commands == [("systemctl", "--user", "stop", "--no-block", "lo9i-assistant")]
    # systemd stops it with SIGTERM; exiting on its own, it would be started again.
    assert not stop.is_set()


class _Backend:
    """A start at boot that's on, started by it or not; records what installing it again did."""

    def __init__(self, managed: bool, enabled: bool = True) -> None:
        self.managed, self.enabled = managed, enabled
        self.done: list[str] = []

    def status(self) -> StartupStatus:
        return StartupStatus(enabled=self.enabled, managed=self.managed, includes_ollama=False)

    async def enable(self) -> StartupStatus:
        self.done.append("enable")
        return self.status()

    async def disable(self) -> StartupStatus:
        return self.status()

    async def install_for_relaunch(self, pid: int) -> None:
        self.done.append(f"relaunch after {pid}")


async def test_installing_again_relaunches_a_daemon_it_started_once_its_runs_end(monkeypatch):
    backend, asked = _Backend(managed=True), []
    monkeypatch.setattr(startup, "_backend", lambda: backend)
    await startup.Startup(asyncio.Event(), asked.append).reinstall()
    assert backend.done == [f"relaunch after {os.getpid()}"] and asked == ["Start at boot was installed again"]


async def test_installing_again_beside_it_installs_as_turning_it_on_and_off_it_refuses(monkeypatch):
    backend = _Backend(managed=False)
    monkeypatch.setattr(startup, "_backend", lambda: backend)
    stop = asyncio.Event()
    await startup.Startup(stop).reinstall()
    assert backend.done == ["enable"]
    backend.enabled = False
    with pytest.raises(StartupError, match="Turn it on instead"):
        await startup.Startup(stop).reinstall()
