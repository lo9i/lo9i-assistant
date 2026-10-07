"""A plugin's own Python environment, built with uv from its uv.lock when it's installed or updated.

Its commands run the environment's scripts directly (`{bin}/<script>`), so each server is one process.
`uv run` would build the environment on the first start, but stays running as the parent of every
server, a second process for each."""

import asyncio
from pathlib import Path

from assistant.core.mcp.servers import McpServerError
from assistant.core.uv import find as find_uv

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
