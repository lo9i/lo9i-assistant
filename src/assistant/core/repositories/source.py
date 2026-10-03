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
    # For a skill that comes with an MCP server (its SKILL.md is in the server's folder): that
    # server, which installs, updates and removes it.
    server: str = ""
    # The version it declared (`version:` in its server.yaml or SKILL.md); "" when it declared none.
    version: str = ""


def read(folder: Path) -> Source | None:
    record = folder / _FILE
    if not record.is_file():
        return None
    data = yaml.safe_load(record.read_text(encoding="utf-8")) or {}
    fields = ("url", "path", "commit", "server", "version")
    return Source(**{f: str(data.get(f, "." if f == "path" else "")) for f in fields})


def write(folder: Path, source: Source) -> None:
    data = {"url": source.url, "path": source.path, "commit": source.commit, "server": source.server}
    data["version"] = source.version
    (folder / _FILE).write_text(yaml.safe_dump(data), encoding="utf-8")
