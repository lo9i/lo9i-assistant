"""`lo9i doctor`: the setup check (core/setup_check/) from a shell. The parts that need nothing but this computer it
checks itself, so it says what's wrong while the daemon is down too; the rest it asks the daemon for when it answers,
never starting it. The command on PATH and the daemon answering are its own: its shell's PATH, the socket it reached."""

import asyncio
import json
import os
from dataclasses import asdict
from pathlib import Path

from lo9i.client import DaemonUnavailableError, connect
from lo9i.client.daemon_client import OlderDaemonError
from lo9i.core import i18n as core_i18n
from lo9i.core.agent import SetupCheck, SetupReport
from lo9i.core.config import settings
from lo9i.core.setup_check import local, merged
from lo9i.daemon.web_ui import BUILD_DIR
from lo9i_terminal import i18n
from lo9i_terminal.setup_check_text import lines


async def doctor(as_json: bool) -> int:
    """Prints the report; 1 when a part fails, as a script checking it expects."""
    report = await _report()
    print(json.dumps(asdict(report), indent=2, ensure_ascii=False) if as_json else lines(report.checks))
    return 1 if report.failed else 0


async def _report() -> SetupReport:
    socket = Path(settings.daemon_socket).expanduser()
    files, command = await asyncio.to_thread(_files), await asyncio.to_thread(local.command, os.environ.get("PATH", ""))
    try:
        async with connect(start=False) as client:
            i18n.use(await client.language.get())
            asked = await client.setup_check.run()
    except DaemonUnavailableError:
        return SetupReport(_shown([local.daemon(False, socket), *files, command]))
    except OlderDaemonError:
        return SetupReport(_shown([local.older_daemon(socket), *files, command]))
    return SetupReport(merged(asked.checks, _shown([local.daemon(True, socket), command])), asked.at)


def _files() -> list[SetupCheck]:
    return [local.web_app(BUILD_DIR), local.disk(Path(settings.database_path).expanduser().parent)]


def _shown(checks: list[SetupCheck]) -> list[SetupCheck]:
    """The core's text in the language the terminal app shows (English while the daemon is down)."""
    return core_i18n.texts(i18n.language()).within(checks)
