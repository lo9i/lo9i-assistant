"""Where an imported skill came from, kept in its folder as `.imported.yaml`: the agent, the source's path and the
digest of its files when it was copied (`found.py`), so the listing can tell it was imported and whether the
source changed since. A hidden file, so it's never one of the skill's files."""

from dataclasses import dataclass
from pathlib import Path

import yaml

_FILE = ".imported.yaml"


@dataclass(frozen=True)
class ImportRecord:
    agent: str
    # The source's path: Found.id.
    path: str
    digest: str


def read(folder: Path) -> ImportRecord | None:
    record = folder / _FILE
    if not record.is_file():
        return None
    data = yaml.safe_load(record.read_text(encoding="utf-8")) or {}
    return ImportRecord(str(data.get("agent", "")), str(data.get("path", "")), str(data.get("digest", "")))


def write(folder: Path, record: ImportRecord) -> None:
    data = {"agent": record.agent, "path": record.path, "digest": record.digest}
    (folder / _FILE).write_text(yaml.safe_dump(data), encoding="utf-8")
