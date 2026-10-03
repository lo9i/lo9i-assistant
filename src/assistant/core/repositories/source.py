"""Where an installed skill or MCP server came from, kept in its folder as `.source.yaml` so it can be
updated."""

from dataclasses import dataclass
from pathlib import Path

import yaml

_FILE = ".source.yaml"


@dataclass(frozen=True)
class Source:
    url: str
    # Its folder inside the repository; "." when the repository is that one thing.
    path: str
    commit: str


def read(folder: Path) -> Source | None:
    record = folder / _FILE
    if not record.is_file():
        return None
    data = yaml.safe_load(record.read_text(encoding="utf-8")) or {}
    return Source(str(data.get("url", "")), str(data.get("path", ".")), str(data.get("commit", "")))


def write(folder: Path, source: Source) -> None:
    data = {"url": source.url, "path": source.path, "commit": source.commit}
    (folder / _FILE).write_text(yaml.safe_dump(data), encoding="utf-8")
