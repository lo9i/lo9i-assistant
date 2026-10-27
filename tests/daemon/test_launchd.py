"""The LaunchDaemon plist and install commands. Nothing is installed: that needs a password."""

import asyncio
import plistlib
import subprocess
import sys
from pathlib import Path

from assistant.daemon import launchd


def test_daemon_plist_runs_this_python_as_this_user_from_boot():
    plist = plistlib.loads(launchd.daemon_plist())
    assert plist["ProgramArguments"] == [sys.executable, "-m", "assistant.daemon"]
    assert plist["RunAtLoad"] and plist["UserName"]
    assert plist["EnvironmentVariables"][launchd.MANAGED_ENV] == "1"


def test_launchd_starts_the_daemon_again_unless_it_stopped_cleanly():
    plist = plistlib.loads(launchd.daemon_plist())
    assert plist["KeepAlive"] == {"SuccessfulExit": False}
    assert plist["EnvironmentVariables"][launchd.STAYS_STOPPED_ENV] == "1"


async def test_a_daemon_from_a_plist_that_keeps_it_stopped_stops_by_exiting(monkeypatch):
    monkeypatch.setenv(launchd.STAYS_STOPPED_ENV, "1")
    stop = asyncio.Event()
    assert launchd.Service().stop_refusal() is None
    await launchd.Service().stop(stop)
    assert stop.is_set()


def test_a_daemon_from_an_older_plist_cant_be_stopped(monkeypatch):
    """Its plist restarts it whatever its exit, so stopping would be a restart."""
    monkeypatch.delenv(launchd.STAYS_STOPPED_ENV, raising=False)
    assert "Turn start at boot off and on" in (launchd.Service().stop_refusal() or "")


def test_install_commands_quote_paths_and_reload():
    commands = launchd.install_commands("com.lo9i.assistant", Path("/tmp/with space/a.plist"))
    assert "cp '/tmp/with space/a.plist' /Library/LaunchDaemons/com.lo9i.assistant.plist" in commands
    assert commands.index("bootout") < commands.index("bootstrap system")


def test_applescript_escaping():
    assert launchd._applescript_escape('echo "a" \\') == 'echo \\"a\\" \\\\'


_MOVE = (
    "import sys; from assistant.daemon import launchd; "
    "print('before', file=sys.stderr, flush=True); moved = launchd.move_legacy_output(); "
    "print('after', moved, file=sys.stderr)"
)


def _start(home: Path, stderr: Path) -> None:
    """A daemon started by an old LaunchDaemon: its stderr is the file the plist names."""
    env = {"HOME": str(home), "LOGS_DIR": str(home / ".lo9i" / "logs"), "PATH": "/usr/bin:/bin"}
    stderr.parent.mkdir(parents=True, exist_ok=True)
    with stderr.open("ab") as out:
        subprocess.run([sys.executable, "-c", _MOVE], env=env, cwd=home, stderr=out, check=True)


def test_output_an_old_launch_daemon_sends_to_the_old_file_moves_to_the_logs_folder(tmp_path):
    _start(tmp_path, tmp_path / ".lo9i" / "daemon.log")
    assert (tmp_path / ".lo9i" / "daemon.log").read_text() == "before\n"
    assert (tmp_path / ".lo9i" / "logs" / "output.log").read_text() == "after True\n"


def test_output_going_anywhere_else_stays(tmp_path):
    _start(tmp_path, tmp_path / "elsewhere.log")
    assert (tmp_path / "elsewhere.log").read_text() == "before\nafter False\n"
    assert not (tmp_path / ".lo9i" / "logs" / "output.log").exists()


def _installed(monkeypatch, tmp_path, plist: dict) -> None:
    monkeypatch.setattr(launchd, "_PLIST_DIR", tmp_path)
    (tmp_path / f"{launchd.DAEMON_LABEL}.plist").write_bytes(plistlib.dumps(plist))


def test_a_launch_daemon_installed_by_an_older_version_says_how_it_differs(monkeypatch, tmp_path):
    old = plistlib.loads(launchd.daemon_plist()) | {"KeepAlive": True, "StandardOutPath": "/Users/me/.lo9i/daemon.log"}
    _installed(monkeypatch, tmp_path, old)
    reasons = launchd.status().outdated
    assert len(reasons) == 2
    assert "can't be stopped from the app" in reasons[0] and "/Users/me/.lo9i/daemon.log" in reasons[1]


def test_the_launch_daemon_installed_now_is_up_to_date(monkeypatch, tmp_path):
    _installed(monkeypatch, tmp_path, plistlib.loads(launchd.daemon_plist()))
    assert launchd.status().outdated == []
    monkeypatch.setattr(launchd, "_PLIST_DIR", tmp_path / "none")
    assert launchd.status().outdated == []


def test_installing_again_under_a_running_daemon_reloads_it_once_that_one_exits():
    commands = launchd.relaunch_commands("com.lo9i.assistant", Path("/tmp/with space/a.plist"), 4242)
    assert commands.startswith("cp '/tmp/with space/a.plist' /Library/LaunchDaemons/com.lo9i.assistant.plist")
    background = commands[commands.index("(while") :]
    assert background.startswith("(while kill -0 4242 2>/dev/null; do sleep 1; done; launchctl bootout")
    assert background.index("bootout") < background.index("bootstrap system") and background.endswith("&")
