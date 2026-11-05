"""The parts of the setup check that need nothing but this computer, so `lo9i doctor` runs them while the daemon is
down too: the daemon answering on its socket, the web app built, free disk space where lo9i keeps its data, and the
lo9i command on PATH. Each reads a few files, quick enough to run in a thread."""

import os
import shutil
from pathlib import Path

from lo9i.core.i18n import said
from lo9i.core.setup_check.model import SetupCheck

# Where install.sh links the command, and where uv's installer puts uv: on PATH in most shells.
COMMAND_LINK = Path("~/.local/bin/lo9i")
COMMAND = "lo9i"
# Below these, free space in the data folder is a warning, then a failure: the database, uploads, models and logs
# grow there, and SQLite fails writes once it's full.
_LOW_BYTES = 5 * 1024**3
_FULL_BYTES = 1024**3
_GB = 1024**3


def daemon(answering: bool, socket: Path) -> SetupCheck:
    title = said("Daemon")
    if answering:
        return SetupCheck("daemon", title, "ok", said("Answering on {socket}.", socket=str(socket)))
    return SetupCheck(
        "daemon",
        title,
        "fail",
        said("Not answering on {socket}.", socket=str(socket)),
        said("Run lo9i to start it; if it doesn't start, see ~/.lo9i/logs/output.log."),
    )


def older_daemon(socket: Path) -> SetupCheck:
    """The daemon answers, running a version from before the setup check: the rest can't be asked of it."""
    return SetupCheck(
        "daemon",
        said("Daemon"),
        "warn",
        said("Answering on {socket}, on an older version that can't check the rest.", socket=str(socket)),
        said("Restart it on this version: lo9i daemon restart."),
    )


def web_app(build: Path) -> SetupCheck:
    title = said("Web app")
    if (build / "index.html").is_file():
        return SetupCheck("web_app", title, "ok", said("Built."))
    return SetupCheck(
        "web_app",
        title,
        "fail",
        said("Not built: /app/ says so instead of opening it."),
        said("Install Node.js (with npm) and run install.sh again; it builds the web app."),
    )


def disk(folder: Path) -> SetupCheck:
    """Free space on the disk holding `folder` (lo9i's data)."""
    title = said("Disk space")
    usage = shutil.disk_usage(_existing(folder))
    free = said("{free} GB free of {total} GB.", free=f"{usage.free / _GB:.1f}", total=f"{usage.total / _GB:.0f}")
    if usage.free < _FULL_BYTES:
        return SetupCheck("disk", title, "fail", free, said("Free some space: lo9i can't save while the disk is full."))
    if usage.free < _LOW_BYTES:
        return SetupCheck("disk", title, "warn", free, said("Free some space before the disk fills up."))
    return SetupCheck("disk", title, "ok", free)


def command(search_path: str | None = None) -> SetupCheck:
    """Whether `lo9i` runs from a shell. `search_path` is the PATH of the shell asking (`lo9i doctor`'s); without it
    (the daemon, whose PATH a service manager sets) the link install.sh makes is enough."""
    title = said("lo9i command")
    found = shutil.which(COMMAND, path=search_path)
    if found:
        return SetupCheck("command", title, "ok", said("On PATH: {path}.", path=found))
    link = COMMAND_LINK.expanduser()
    if link.is_symlink() and not link.exists():
        return SetupCheck(
            "command",
            title,
            "fail",
            said("{link} leads to {target}, which isn't there any more.", link=str(link), target=os.readlink(link)),
            said("Run install.sh again: it links lo9i into ~/.local/bin."),
        )
    if link.exists():
        if search_path is None:
            return SetupCheck("command", title, "ok", said("Linked in {folder}.", folder=str(link.parent)))
        return SetupCheck(
            "command",
            title,
            "warn",
            said("Linked in {folder}, which isn't on this shell's PATH.", folder=str(link.parent)),
            said("Open a new terminal, or add {folder} to PATH in your shell's profile.", folder=str(link.parent)),
        )
    return SetupCheck(
        "command",
        title,
        "warn",
        said("Not on PATH."),
        said("Run install.sh again: it links lo9i into ~/.local/bin."),
    )


def _existing(folder: Path) -> Path:
    """`folder`, or its nearest parent that exists: before the daemon's first start there's no data folder yet."""
    while not folder.exists() and folder != folder.parent:
        folder = folder.parent
    return folder
