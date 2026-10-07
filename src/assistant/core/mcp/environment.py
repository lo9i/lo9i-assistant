"""A plugin's own Python environment, built with uv from its uv.lock when it's installed or updated.

Its commands run the environment's scripts directly (`{bin}/<script>`), so each server is one process.
`uv run` would build the environment on the first start, but stays running as the parent of every
server, a second process for each. Before each start, `Environments.ensure` builds it again if it was
lost or broke (the folder deleted, the Python uv built it with removed)."""

import asyncio
import logging
from collections import defaultdict
from collections.abc import Callable
from pathlib import Path

from assistant.core.mcp.servers import McpServerError
from assistant.core.uv import find as find_uv

logger = logging.getLogger(__name__)

PLACEHOLDER = "{bin}"


def scripts(folder: Path) -> Path:
    """Where the environment's scripts are: what `{bin}` stands for."""
    return folder / ".venv" / "bin"


async def build(name: str, folder: Path) -> None:
    """Installs the locked dependencies into `folder/.venv`. Raises McpServerError if uv is missing or fails."""
    uv = find_uv()
    if uv is None:
        raise McpServerError(f"{name} runs in its own environment, and the assistant can't find uv on this computer.")
    process = await asyncio.create_subprocess_exec(
        uv,
        "sync",
        "--quiet",
        "--frozen",
        "--project",
        str(folder),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    _, errors = await process.communicate()
    if process.returncode != 0:
        raise McpServerError(f"Couldn't install what {name} needs: {errors.decode(errors='replace').strip()}")


class Environments:
    """Rebuilds a plugin's environment when a process is about to start from it and it can't run.
    One build at a time per plugin: its server, page and channel may start together."""

    def __init__(self, code: Callable[[str], Path]) -> None:
        """`code` gives a plugin's folder by name (core/mcp/folders.py)."""
        self._code = code
        self._locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    async def ensure(self, name: str, command: str) -> None:
        """Raises McpServerError if the environment `command` runs from had to be rebuilt and couldn't be."""
        folder = self._code(name)
        if Path(command).parent != scripts(folder):
            return
        async with self._locks[name]:
            if await asyncio.to_thread(_runs, Path(command)):
                return
            logger.warning("The environment of %s is missing or broken; building it again", name)
            await build(name, folder)


def _runs(command: Path) -> bool:
    """The script is there, and so is the Python it runs with (a link uv made, broken if that Python is gone)."""
    return command.is_file() and (command.parent / "python").exists()
