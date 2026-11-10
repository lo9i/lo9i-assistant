"""CLI entry point (its arguments in cli.py). `lo9i` opens the chat, starting the daemon if it isn't running, after
what the checkout's scripts/prepare.sh does (Ollama, the web app built); `lo9i daemon` runs the daemon in the
foreground; `lo9i daemon restart` restarts the running one once no run is in progress; `lo9i doctor` checks the
setup (setup_check_command.py); `lo9i export` and `lo9i import` move lo9i to another computer
(migration_command.py); `lo9i completion <shell>` prints a completion script."""

import asyncio
import subprocess
import sys
from pathlib import Path

from lo9i.client import DaemonClient, DaemonUnavailableError, connect
from lo9i.core.agent import Session
from lo9i.core.config import settings
from lo9i_terminal import i18n, migration_command
from lo9i_terminal.cli import CHECKOUT, Command, parse
from lo9i_terminal.completion import script
from lo9i_terminal.history import History
from lo9i_terminal.i18n import t
from lo9i_terminal.preferences import Preferences
from lo9i_terminal.repl import Repl
from lo9i_terminal.setup_check_command import doctor
from lo9i_terminal.tui.app import AssistantApp


async def _chat() -> None:
    async with connect() as client:
        i18n.use(await client.language.get())
        # Every terminal opens on the inbox, which routes each message to its conversation; /clear starts one,
        # /conversations opens one.
        session = Session(settings.owner_id, "cli", await client.inbox_thread(settings.owner_id))
        await _open(client, session)


async def _open(client: DaemonClient, session: Session) -> None:
    if sys.stdin.isatty() and sys.stdout.isatty():
        history = History(Path(settings.cli_history_path).expanduser(), settings.cli_history_limit)
        preferences = Preferences(Path(settings.cli_preferences_path).expanduser())
        await AssistantApp(client, session, history, preferences).run_async(mouse=preferences.mouse)
    else:
        await Repl(client, session).loop()


async def _restart() -> None:
    async with connect() as client:
        i18n.use(await client.language.get())
        waiting = (await client.system.restart()).waiting_for_runs
    print(
        t("The daemon restarts once the {count} runs in progress end.", count=waiting)
        if waiting
        else t("The daemon restarts now.")
    )


def run() -> int:
    command = parse(sys.argv[1:])
    match command.name:
        case "completion":
            print(script(command.argument), end="")
            return 0
        case "daemon" if not command.argument:
            from lo9i.daemon.server import run as run_daemon

            run_daemon()
            return 0
        case "chat":
            _prepare()
    try:
        return asyncio.run(_command(command))
    except DaemonUnavailableError as e:
        sys.exit(str(e))


async def _command(command: Command) -> int:
    match command.name:
        case "doctor":
            return await doctor(command.json)
        case "export":
            return await migration_command.export(command.argument)
        case "import":
            return await migration_command.import_(command.argument, command.force)
        case "daemon":
            await _restart()
        case _:
            await _chat()
    return 0


def _prepare() -> None:
    """Ollama started and the web app built, as scripts/run.sh did before opening the chat; a checkout without the
    script (an installed package) has neither to do."""
    prepare = CHECKOUT / "scripts" / "prepare.sh"
    if prepare.is_file() and subprocess.run([str(prepare)]).returncode != 0:
        sys.exit(1)
