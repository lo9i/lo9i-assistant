"""`lo9i security audit`: the security audit (core/security_audit/) from a shell. The local parts (ports, socket,
permissions, bash approval) it reads itself, so it reports them while the daemon is down too; with the daemon
answering it asks it for the whole audit, paired devices and what plugins run here included, never starting it."""

import asyncio
import json
from dataclasses import asdict
from pathlib import Path

from lo9i.client import DaemonUnavailableError, connect
from lo9i.client.daemon_client import OlderDaemonError
from lo9i.core import i18n as core_i18n
from lo9i.core.agent import SetupCheck, SetupReport
from lo9i.core.config import settings
from lo9i.core.security_audit import local
from lo9i.core.setup_check import local as setup_local
from lo9i_terminal import i18n
from lo9i_terminal.setup_check_text import lines


async def audit(as_json: bool) -> int:
    """Prints the report; 1 when a part fails, as a script checking it expects."""
    report = await _report()
    print(json.dumps(asdict(report), indent=2, ensure_ascii=False) if as_json else lines(report.checks))
    return 1 if report.failed else 0


async def _report() -> SetupReport:
    socket = Path(settings.daemon_socket).expanduser()
    try:
        async with connect(start=False) as client:
            i18n.use(await client.language.get())
            return _shown(await client.security.audit())
    except DaemonUnavailableError:
        down = setup_local.daemon(False, socket)
    except OlderDaemonError:
        down = setup_local.older_daemon(socket)
    found = await asyncio.to_thread(local.checks)
    return _shown(SetupReport([_partial(down), *found]))


def _partial(down: SetupCheck) -> SetupCheck:
    """The daemon not answering is a warning here: the local parts still say what they can."""
    return SetupCheck(down.id, down.title, "warn", down.detail, down.fix)


def _shown(report: SetupReport) -> SetupReport:
    """The core's text in the language the terminal app shows (English while the daemon is down)."""
    return core_i18n.texts(i18n.language()).within(report)
