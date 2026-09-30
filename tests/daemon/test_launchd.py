"""The LaunchDaemon plist and install commands. Nothing is installed: that needs a password."""

import plistlib
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
