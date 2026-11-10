"""How a move to another computer over SSH is going (daemon/moves.py runs it): its steps, each waiting, running,
done, skipped or failed, with a line on where it got to, and in the end what to set up again there or why it
stopped."""

from dataclasses import dataclass, field

from lo9i.core.i18n import said

# The steps, in the order they run.
CONNECT = "connect"
INSTALL = "install"
EXPORT = "export"
COPY = "copy"
IMPORT = "import"
CLEAN = "clean"

_ORDER = (CONNECT, INSTALL, EXPORT, COPY, IMPORT, CLEAN)


@dataclass
class MoveStep:
    key: str
    label: str
    # waiting, running, done, skipped or failed.
    state: str = "waiting"
    # Where it got to (megabytes copied, what install.sh says), or why it was skipped or failed.
    detail: str = ""


@dataclass
class MoveStatus:
    # "" before any move, then running, done, failed or cancelled.
    state: str = ""
    host: str = ""
    steps: list[MoveStep] = field(default_factory=list)
    # How far the step running is, from 0 to 1; -1 when it can't say.
    progress: float = -1
    to_redo: list[str] = field(default_factory=list)
    error: str = ""


def started(host: str) -> MoveStatus:
    labels = {
        CONNECT: said("Signing in to {host}", host=host),
        INSTALL: said("Installing lo9i there"),
        EXPORT: said("Exporting lo9i's data"),
        COPY: said("Copying the export there"),
        IMPORT: said("Importing it there; lo9i restarts with it"),
        CLEAN: said("Deleting the copied file"),
    }
    return MoveStatus("running", host, [MoveStep(key, labels[key]) for key in _ORDER])
