"""The `lo9i` command's arguments: what to do, and its --help, --version and shell completion, which completion.py
writes from the same commands."""

import argparse
import subprocess
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path
from typing import Literal

import lo9i

SHELLS = ("bash", "zsh", "fish")
# Each command with what it does, as --help and the completion scripts list them.
COMMANDS = {
    "daemon": "Run the daemon in the foreground; `lo9i daemon restart` restarts the running one.",
    "doctor": "Check that lo9i is installed and set up to work.",
    "export": "Export lo9i's data, sealed with a password, to move it to another computer.",
    "import": "Import an export here; the daemon restarts to use it.",
    "completion": "Print the shell completion script for bash, zsh or fish.",
}
DAEMON_ACTIONS = ("restart",)
# The checkout lo9i runs from (src/lo9i/__init__.py's), with its scripts and .git.
CHECKOUT = Path(lo9i.__file__).resolve().parents[2]


@dataclass(frozen=True)
class Command:
    # chat: open the terminal app (no command given).
    name: Literal["chat", "daemon", "doctor", "export", "import", "completion"]
    # daemon: "restart", or "" to run it. completion: the shell. export: where to write it, "" for the folder it runs
    # in. import: the export.
    argument: str = ""
    # doctor: print the report as JSON.
    json: bool = False
    # import: set aside the data lo9i has here.
    force: bool = False


def parse(args: list[str]) -> Command:
    """Exits after printing --help, --version or a usage error, as argparse does."""
    found = _parser().parse_args(args)
    match found.command:
        case None:
            return Command("chat")
        case "daemon":
            return Command("daemon", found.action or "")
        case "doctor":
            return Command("doctor", json=found.json)
        case "export":
            return Command("export", found.path or "")
        case "import":
            return Command("import", found.file, force=found.force)
        case _:
            return Command("completion", found.shell)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lo9i",
        description="Your assistant. Without a command, opens the chat, starting the daemon if it isn't running.",
    )
    parser.add_argument("--version", action=_Version, nargs=0, help="show the version and exit")
    commands = parser.add_subparsers(dest="command", metavar="command")
    daemon = commands.add_parser("daemon", help=COMMANDS["daemon"], description=COMMANDS["daemon"])
    daemon.add_argument("action", nargs="?", choices=DAEMON_ACTIONS, help="restart the running daemon")
    doctor = commands.add_parser("doctor", help=COMMANDS["doctor"], description=COMMANDS["doctor"])
    doctor.add_argument("--json", action="store_true", help="print the report as JSON")
    exporting = commands.add_parser("export", help=COMMANDS["export"], description=COMMANDS["export"])
    exporting.add_argument("path", nargs="?", help="the file or folder to write it to (the current folder if absent)")
    importing = commands.add_parser("import", help=COMMANDS["import"], description=COMMANDS["import"])
    importing.add_argument("file", help="the export")
    importing.add_argument(
        "--force", action="store_true", help="replace the data lo9i has here, which is kept in a folder beside it"
    )
    completion = commands.add_parser("completion", help=COMMANDS["completion"], description=COMMANDS["completion"])
    completion.add_argument("shell", choices=SHELLS)
    return parser


class _Version(argparse.Action):
    """argparse's own reads the version when the parser is made; this asks git only when --version is given."""

    def __call__(self, parser: argparse.ArgumentParser, *_: object) -> None:
        print(f"lo9i {version_text()}")
        parser.exit()


def version_text() -> str:
    """The package's version, and the commit a git checkout is on."""
    commit = _commit()
    return f"{version('lo9i')} ({commit})" if commit else version("lo9i")


def _commit() -> str:
    try:
        found = subprocess.run(
            ["git", "-C", str(CHECKOUT), "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=5
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return found.stdout.strip() if found.returncode == 0 else ""
