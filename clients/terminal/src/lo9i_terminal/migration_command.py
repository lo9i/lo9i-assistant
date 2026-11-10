"""`lo9i export [path]` and `lo9i import <file>`: moving lo9i to another computer from a shell, through the daemon
(core/migration/), which `lo9i import` starts on a fresh install."""

import getpass
import sys
from datetime import date
from pathlib import Path

from lo9i.client import connect
from lo9i.core.agent import HomeInUseError, ImportReport, MigrationError
from lo9i_terminal import i18n
from lo9i_terminal.i18n import t


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


async def import_(path: str, force: bool) -> int:
    source = Path(path).expanduser()
    if not source.is_file():
        sys.exit(t("There's no file at {path}.", path=str(source)))
    password = getpass.getpass(t("The export's password: "))
    async with connect() as client:
        i18n.use(await client.language.get())
        print(t("Importing {path}…", path=str(source)))
        try:
            report = await client.migration.import_from(source, password, replace=force)
        except HomeInUseError as e:
            sys.exit(f"{e}\n{t('Run it again with --force to replace it.')}")
        except MigrationError as e:
            sys.exit(str(e))
    print(_reported(report))
    return 0


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
