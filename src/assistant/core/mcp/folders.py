"""Where an MCP server installed from a repository lives: its code, which updates replace, and its
data, which they keep."""

import logging
import shutil
from pathlib import Path

from assistant.core.config import settings

logger = logging.getLogger(__name__)

# The socket a server's page listens on, in its data folder: only the user can open that folder.
PAGE_SOCKET = "page.sock"


def code(name: str) -> Path:
    return Path(settings.mcp_dir).expanduser() / name


def data(name: str) -> Path:
    return Path(settings.mcp_data_dir).expanduser() / name


def page_socket(name: str) -> Path:
    return data(name) / PAGE_SOCKET


def remove_old_libraries() -> None:
    """Removes the shared libraries plugins used to install next to their folders (`~/.lo9i/lib/`).
    Plugins share no code any more, so nothing uses them. Blocks: async code calls it in a thread."""
    libraries = Path(settings.mcp_dir).expanduser().parent / "lib"
    if not libraries.is_dir():
        return
    shutil.rmtree(libraries)
    logger.info("Removed %s: plugins no longer share libraries.", libraries)
