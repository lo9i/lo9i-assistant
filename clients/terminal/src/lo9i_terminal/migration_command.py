"""`lo9i export [path]` and `lo9i import <file>`: moving lo9i to another computer from a shell, through the daemon
(core/migration/), which `lo9i import` starts on a fresh install. A move over SSH (`lo9i migrate`) runs `lo9i import`
there with --password-stdin, --json and --wait."""

import asyncio
import getpass
import json
import sys
from dataclasses import asdict
from datetime import date
from pathlib import Path

from lo9i.client import DaemonClient, connect
from lo9i.core.agent import HomeInUseError, ImportReport, MigrationError
from lo9i_terminal import i18n
from lo9i_terminal.i18n import t

# What `lo9i import` exits with when lo9i has data here (core/migration/remote.py reads it).
HOME_IN_USE = 3
# How long --wait waits for the daemon to restart with the import.
_RESTART_SECONDS = 600


async def export(path: str) -> int:
    target = _target(path)
    password = _new_password()
    if password is None:
        return 1
    async with connect() as client:
        i18n.use(await client.language.get())
        print(t("Exporting to {path}…", path=str(target)))
        try:
            await client.migration.export_to(target, password)
        except MigrationError as e:
            sys.exit(str(e))
    print(t("Done. Copy it to the other computer and run: lo9i import {name}", name=target.name))
    return 0


async def import_(
    path: str, force: bool, password_stdin: bool = False, as_json: bool = False, wait: bool = False
) -> int:
    source = Path(path).expanduser()
    if not source.is_file():
        sys.exit(t("There's no file at {path}.", path=str(source)))
    password = sys.stdin.readline().rstrip("\n") if password_stdin else getpass.getpass(t("The export's password: "))
    async with connect() as client:
        i18n.use(await client.language.get())
        print(t("Importing {path}…", path=str(source)), file=sys.stderr)
        try:
            report = await _imported(client, source, password, force, wait)
        except HomeInUseError as e:
            print(f"{e}\n{t('Run it again with --force to replace it.')}", file=sys.stderr)
            return HOME_IN_USE
        except MigrationError as e:
            sys.exit(str(e))
    print(json.dumps(asdict(report), ensure_ascii=False) if as_json else _reported(report))
    return 0


async def _imported(client: DaemonClient, source: Path, password: str, force: bool, wait: bool) -> ImportReport:
    if not wait:
        return await client.migration.import_from(source, password, replace=force)
    restart = _Restart(client)
    following = asyncio.create_task(restart.follow())
    try:
        # Following before importing: a restart that comes first is seen all the same.
        await restart.opened.wait()
        report = await client.migration.import_from(source, password, replace=force)
        try:
            await asyncio.wait_for(restart.back.wait(), _RESTART_SECONDS)
        except TimeoutError:
            sys.exit(t("The daemon didn't restart within {minutes} minutes.", minutes=_RESTART_SECONDS // 60))
        return report
    finally:
        following.cancel()


class _Restart:
    """The daemon's event stream, followed to tell when the daemon went away and came back."""

    def __init__(self, client: DaemonClient) -> None:
        self._client = client
        self.opened = asyncio.Event()
        self._lost = asyncio.Event()
        self.back = asyncio.Event()

    async def follow(self) -> None:
        async for _ in self._client.events(on_open=self._open, on_lost=self._lost.set):
            pass

    def _open(self) -> None:
        (self.back if self._lost.is_set() else self.opened).set()


def _target(path: str) -> Path:
    """The file to write: `path`, or the export's usual name in it when it's a folder ("" for the current one)."""
    target = Path(path or ".").expanduser()
    return target / f"lo9i-export-{date.today().isoformat()}.tar.gz.enc" if target.is_dir() else target


def _new_password() -> str | None:
    password = getpass.getpass(t("A password for the export (you'll need it to import it): "))
    if getpass.getpass(t("The same password again: ")) != password:
        print(t("The passwords don't match."), file=sys.stderr)
        return None
    return password


def _reported(report: ImportReport) -> str:
    restart = (
        t("The daemon restarts to use it once the {count} runs in progress end.", count=report.waiting_for_runs)
        if report.waiting_for_runs
        else t("The daemon restarts now to use it.")
    )
    lines = [
        t(
            "Imported the export of {host} ({system}) from {when}.",
            host=report.host,
            system=report.system,
            when=report.exported_at,
        ),
        restart,
        "",
        t("To do on this computer:"),
        *(f"- {item}" for item in report.to_redo),
    ]
    return "\n".join(lines)
