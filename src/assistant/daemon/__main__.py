"""`python -m assistant.daemon`, from before the package was named lo9i: a LaunchDaemon or systemd service installed
then starts it, and a daemon started then restarts in place with the command it was started with
(lo9i/daemon/shutdown.py::exec_again). It becomes `python -m lo9i.daemon`, the same process, so its later restarts
start that. Installing start at boot again (Install again, /startup) moves a service off it."""

import os
import sys

os.execv(sys.executable, [sys.executable, "-m", "lo9i.daemon", *sys.argv[1:]])
