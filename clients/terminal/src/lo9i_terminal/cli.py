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
    "migrate": "Move lo9i to another computer over SSH, installing it there if it's missing.",
    "clean": "Show the disk lo9i takes and what cleaning would free; --yes cleans it.",
    "completion": "Print the shell completion script for bash, zsh or fish.",
}
DAEMON_ACTIONS = ("restart",)
# What `lo9i clean` can be told to clean (core/disk/); the downloads only when named.
CLEANED = ("database", "logs", "backups", "uploads", "plugins", "plugin_data", "downloads")
# The checkout lo9i runs from (src/lo9i/__init__.py's), with its scripts and .git.
CHECKOUT = Path(lo9i.__file__).resolve().parents[2]


@dataclass(frozen=True)
class Command:
    # chat: open the terminal app (no command given).
    name: Literal["chat", "daemon", "doctor", "export", "import", "migrate", "clean", "completion"]
    # daemon: "restart", or "" to run it. completion: the shell. export: where to write it, "" for the folder it runs
    # in. import: the export. migrate: the host.
    argument: str = ""
    # doctor, import and clean: print the report as JSON.
    json: bool = False
    # import and migrate: set aside the data lo9i has there.
    force: bool = False
    # import: read the password from the input (a move over SSH gives it so), and wait until the daemon restarted.
    password_stdin: bool = False
    wait: bool = False
    # migrate: how to sign in, and whether to ask for a password.
    user: str = ""
    port: int = 0
    key: str = ""
    password: bool = False
    # clean: the categories to clean (all but the downloads when empty), and whether to clean them or only say so.
    categories: tuple[str, ...] = ()
    yes: bool = False


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
            return Command(
                "import",
                found.file,
                json=found.json,
                force=found.force,
                password_stdin=found.password_stdin,
                wait=found.wait,
            )
        case "migrate":
            return _migrate(found)
        case "clean":
            return Command("clean", json=found.json, categories=tuple(found.categories), yes=found.yes)
        case _:
            return Command("completion", found.shell)


def _migrate(found: argparse.Namespace) -> Command:
    return Command(
        "migrate",
        found.host,
        force=found.replace,
        user=found.user or "",
        port=found.port or 0,
        key=found.key or "",
        password=found.password,
    )


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
    importing.add_argument("--password-stdin", action="store_true", help="read the password from the input")
    importing.add_argument("--json", action="store_true", help="print what to set up again as JSON")
    importing.add_argument("--wait", action="store_true", help="wait until the daemon restarted with it")
    _add_migrate(commands)
    _add_clean(commands)
    completion = commands.add_parser("completion", help=COMMANDS["completion"], description=COMMANDS["completion"])
    completion.add_argument("shell", choices=SHELLS)
    return parser


def _add_migrate(commands: argparse._SubParsersAction) -> None:
    migrate = commands.add_parser("migrate", help=COMMANDS["migrate"], description=COMMANDS["migrate"])
    migrate.add_argument("host", help="its address or ssh name, or a host the hosts plugin keeps")
    migrate.add_argument("--user", help="the user to sign in as")
    migrate.add_argument("--port", type=int, help="its SSH port")
    migrate.add_argument("--key", help="a private key file on this computer to sign in with (never copied)")
    migrate.add_argument("--password", action="store_true", help="ask for the password to sign in with")
    migrate.add_argument(
        "--replace", action="store_true", help="replace the data lo9i has there, which is kept in a folder beside it"
    )


def _add_clean(commands: argparse._SubParsersAction) -> None:
    clean = commands.add_parser("clean", help=COMMANDS["clean"], description=COMMANDS["clean"])
    clean.add_argument(
        "categories",
        nargs="*",
        choices=CLEANED,
        metavar="category",
        help=f"what to clean, of {', '.join(CLEANED)} (all but downloads if none is given)",
    )
    clean.add_argument("--yes", action="store_true", help="clean it, instead of only saying what it would free")
    clean.add_argument("--json", action="store_true", help="print the report as JSON")


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
