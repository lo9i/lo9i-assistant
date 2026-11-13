"""`lo9i clean`: the disk lo9i takes, by category, and what cleaning would free (core/disk/), through the daemon,
which owns the data. It only says what it would do until it's given --yes; the plugins' downloads are cleaned only when
named."""

import json
import sys
from dataclasses import asdict

from lo9i.client import connect
from lo9i.core.agent import CleanReport, DiskCategory, DiskReport, UnknownCategoryError
from lo9i_terminal import i18n
from lo9i_terminal.files_text import size
from lo9i_terminal.i18n import t, translatable

_NAMES = {
    "database": translatable("Database"),
    "models": translatable("Models"),
    "plugins": translatable("Plugins"),
    "browsers": translatable("Browsers"),
    "plugin_data": translatable("Plugins' data"),
    "uploads": translatable("Uploads"),
    "logs": translatable("Logs"),
    "workspace": translatable("Workspaces"),
    "backups": translatable("Backups"),
    "downloads": translatable("Downloads"),
    "other": translatable("Other"),
}
_CLEANS = {
    "database": translatable("its free space, compacted"),
    "logs": translatable("old logs"),
    "backups": translatable("old copies of lo9i's data"),
    "uploads": translatable("uploads no conversation refers to"),
    "plugins": translatable("caches in plugins' folders"),
    "plugin_data": translatable("caches in plugins' data"),
    "downloads": translatable("plugins' finished downloads"),
}


async def clean(categories: list[str], apply: bool, as_json: bool) -> int:
    async with connect() as client:
        i18n.use(await client.language.get())
        try:
            done = await client.disk.clean(categories) if apply else None
            report = done.usage if done else await client.disk.usage()
        except UnknownCategoryError as e:
            sys.exit(str(e))
    if as_json:
        print(json.dumps(asdict(done or report), indent=2, ensure_ascii=False))
    else:
        print("\n".join(cleaned(done) if done else planned(report, categories)))
    return 1 if done and done.failed else 0


def usage(report: DiskReport) -> list[str]:
    """Each category that takes anything, largest first, with what cleaning it frees."""
    shown = sorted((c for c in report.categories if c.bytes), key=lambda c: -c.bytes)
    width = max((len(t(_NAMES[c.name])) for c in shown), default=0)
    lines = [t("lo9i takes {size} in {home}:", size=size(report.total), home=report.home)]
    return lines + [f"  {t(_NAMES[c.name]):<{width}}  {size(c.bytes):>9}{_freeable(c)}" for c in shown]


def _freeable(category: DiskCategory) -> str:
    return f"   {t('{size} to free', size=size(category.freeable))}" if category.freeable else ""


def planned(report: DiskReport, categories: list[str]) -> list[str]:
    """The usage, then what cleaning `categories` (every one but the downloads when empty) would remove."""
    picked = [c for c in report.categories if c.freeable and (c.name in categories or not (categories or c.on_request))]
    chosen = sorted(picked, key=lambda c: -c.freeable)
    lines = [*usage(report), ""]
    if not chosen:
        return [*lines, t("Nothing to clean.")]
    freed = sum(c.freeable for c in chosen)
    lines.append(t("Cleaning would free {size}:", size=size(freed)))
    lines += [f"  {t(_NAMES[c.name])}: {size(c.freeable)}, {t(_CLEANS[c.name])}" for c in chosen]
    lines += _downloads_note(report, categories)
    return [*lines, "", t("Nothing was removed. Run it again with --yes to clean.")]


def _downloads_note(report: DiskReport, categories: list[str]) -> list[str]:
    downloads = next(c for c in report.categories if c.name == "downloads")
    if not downloads.freeable or "downloads" in categories:
        return []
    return [
        t(
            "Plugins' downloads ({size}) are cleaned only when named: lo9i clean downloads",
            size=size(downloads.freeable),
        )
    ]


def cleaned(done: CleanReport) -> list[str]:
    lines = [t("Freed {size}.", size=size(done.freed))]
    lines += [t("Couldn't clean {path}: {reason}", path=f.path, reason=f.reason) for f in done.failed]
    return [*lines, "", *usage(done.usage)]
