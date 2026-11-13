"""Files a plugin downloads outside lo9i's data home, for disk use to count them and clean them when the user asks:
`downloads:` in its server.yaml says where they go and which of the files there are its own (docs/plugin-downloads.md).

    downloads:
      field: YOUTUBE_DIR               # the field whose value is the folder
      default: ~/Downloads             # the folder while that field is empty; {data} is the plugin's data folder
      files: ['.* \\[[\\w-]{11}\\]\\.(mp4|mp3)']   # regular expressions a file's whole name matches

It's read from the plugin's installed folder each time, so a plugin installed before it declared one counts once it's
updated. An older daemon doesn't know the section and only doesn't count them, so it needs no format of its own."""

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from langgraph.store.base import BaseStore

from lo9i.core.mcp import folders, keys, servers
from lo9i.core.mcp.servers import McpServer
from lo9i.core.repositories.folders import SERVER_FILE
from lo9i.core.secret_store import SecretBox

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DownloadsFolder:
    plugin: str
    folder: Path
    files: tuple[re.Pattern[str], ...]

    def finished(self) -> list[Path]:
        """The plugin's files at the top of the folder: a download in progress has a name of its own until it's done
        (yt-dlp's .part), which the plugin's patterns leave out."""
        try:
            found = [p for p in self.folder.iterdir() if p.is_file() and not p.is_symlink()]
        except OSError:
            return []
        return sorted(p for p in found if any(pattern.fullmatch(p.name) for pattern in self.files))


async def every(store: BaseStore, box: SecretBox) -> list[DownloadsFolder]:
    """Each installed plugin's that declares one. One that can't be read is logged and left out."""
    found: list[DownloadsFolder] = []
    for server in await servers.load_all(store):
        if server.source:
            declared = _declared(await keys.fill(store, box, server))
            found += [declared] if declared else []
    return found


def _declared(server: McpServer) -> DownloadsFolder | None:
    try:
        data = yaml.safe_load((folders.code(server.name) / SERVER_FILE).read_text(encoding="utf-8")) or {}
        section = data.get("downloads")
        return parse(server.name, section, server.env) if section else None
    except (OSError, yaml.YAMLError, TypeError, ValueError, re.error) as e:
        logger.warning("Couldn't read where %s's downloads go: %s", server.name, e)
        return None


def parse(plugin: str, section: Any, env: dict[str, str]) -> DownloadsFolder:
    """Raises ValueError for a section that isn't one, re.error for a pattern that isn't one."""
    if not isinstance(section, dict) or not isinstance(files := section.get("files"), list) or not files:
        raise ValueError("its downloads section needs files, a list of patterns")
    given = env.get(str(section.get("field", "")), "").strip()
    folder = given or str(section.get("default", "")).replace("{data}", str(folders.data(plugin)))
    if not folder:
        raise ValueError("its downloads section needs a field with a value or a default")
    return DownloadsFolder(plugin, Path(folder).expanduser(), tuple(re.compile(str(f)) for f in files))
