"""Installing a model provider's package the first time it's chosen, into the daemon's own
environment, with uv. LangChain's core stays at the version the assistant was installed with."""

import asyncio
import importlib
import importlib.metadata
import importlib.util
import logging
import sys

from assistant.core.llm.providers import ModelProvider
from assistant.core.uv import find as find_uv

logger = logging.getLogger(__name__)

_TIMEOUT = 600


class PackageError(Exception):
    """A provider's package couldn't be installed. The text says why."""


def installed(provider: ModelProvider) -> bool:
    return not provider.package or importlib.util.find_spec(provider.module) is not None


async def ensure(provider: ModelProvider) -> None:
    """Install the provider's package if it isn't. Raises PackageError."""
    if installed(provider):
        return
    uv = find_uv()
    if uv is None:
        raise PackageError(f"Using {provider.name} needs uv on this computer, to install {provider.package}.")
    logger.info("Installing %s for %s", provider.package, provider.name)
    await _run(uv, "pip", "install", "--python", sys.executable, provider.package, _pinned_core())
    importlib.invalidate_caches()
    if not installed(provider):
        raise PackageError(f"Installed {provider.package}, but {provider.module} still can't be imported.")


def _pinned_core() -> str:
    # The provider must work with the LangChain the assistant runs, not upgrade it under it.
    return f"langchain-core=={importlib.metadata.version('langchain-core')}"


async def _run(*command: str) -> None:
    proc = await asyncio.create_subprocess_exec(
        *command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
    )
    try:
        output, _ = await asyncio.wait_for(proc.communicate(), _TIMEOUT)
    except TimeoutError as e:
        proc.kill()
        await proc.wait()
        raise PackageError(f"Installing didn't finish within {_TIMEOUT // 60} minutes.") from e
    if proc.returncode != 0:
        lines = output.decode(errors="replace").strip().splitlines()
        raise PackageError(f"Couldn't install it: {lines[-1] if lines else 'uv failed'}")
