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
    "completion": "Print the shell completion script for bash, zsh or fish.",
}
DAEMON_ACTIONS = ("restart",)
# The checkout lo9i runs from (src/lo9i/__init__.py's), with its scripts and .git.
CHECKOUT = Path(lo9i.__file__).resolve().parents[2]


@dataclass(frozen=True)
class Command:
    # chat: open the terminal app (no command given).
    name: Literal["chat", "daemon", "doctor", "completion"]
    # daemon: "restart", or "" to run it. completion: the shell.
    argument: str = ""
    # doctor: print the report as JSON.
    json: bool = False


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
