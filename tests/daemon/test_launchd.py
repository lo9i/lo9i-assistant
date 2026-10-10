"""The LaunchDaemon plist and install commands. Nothing is installed: that needs a password."""

import plistlib
import subprocess
import sys
from pathlib import Path

from assistant.daemon import launchd


def test_daemon_plist_runs_this_python_as_this_user_from_boot():
    plist = plistlib.loads(launchd.daemon_plist())
    assert plist["ProgramArguments"] == [sys.executable, "-m", "assistant.daemon"]
    assert plist["RunAtLoad"] and plist["KeepAlive"] and plist["UserName"]
    assert plist["EnvironmentVariables"][launchd.MANAGED_ENV] == "1"


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
