"""Start at boot on Linux: the systemd user service, what status reads, and the commands that turn it
on and off. systemctl and loginctl are faked; nothing is installed."""

import asyncio
import sys
from pathlib import Path

import pytest

from assistant.daemon import startup, systemd
from assistant.protocol import StartupError


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
