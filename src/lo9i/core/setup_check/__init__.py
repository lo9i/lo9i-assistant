"""The setup check: whether lo9i is installed and set up to work, each part ok, a warning or failing, with a one-line
fix. `lo9i doctor` runs it in a terminal, and the apps' Health tab with Check setup. Not the doctor (core/doctor/),
which reads a day's log and conversations for what went wrong in them.

Some parts need nothing but this computer (local.py: the daemon answering, the web app built, free disk space, the
lo9i command on PATH), so the command runs them itself while the daemon is down; the rest read the daemon's own
state (service.py: the model and its key, the plugins, email accounts, chat channels), which the daemon checks
(core/agent/setup_check.py, `GET /setup-check`)."""

from lo9i.core.setup_check.model import SetupCheck, SetupReport, Status, merged

__all__ = ["SetupCheck", "SetupReport", "Status", "merged"]
