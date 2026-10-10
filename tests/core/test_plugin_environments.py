"""A plugin's own environment: built again before a process starts from it when it's lost or broken."""

import asyncio
import logging
import shutil

import pytest

from assistant.core.mcp import environment
from assistant.core.mcp.environment import Environments
from assistant.core.mcp.process import ProcessSpec, keep_running
from assistant.core.mcp.servers import McpServerError
from assistant.core.uv import find as find_uv

_PROJECT = """
[project]
name = "ledger"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = []

[tool.uv]
package = false
"""


async def _plugin(tmp_path):
    folder = tmp_path / "ledger"
    folder.mkdir()
    (folder / "pyproject.toml").write_text(_PROJECT)
    lock = await asyncio.create_subprocess_exec(find_uv() or "uv", "lock", "--offline", "--quiet", cwd=folder)
    assert await lock.wait() == 0
    return folder


async def test_a_lost_environment_is_built_again_before_a_start(tmp_path):
    folder = await _plugin(tmp_path)
    environments = Environments(lambda name: tmp_path / name)
    python = environment.scripts(folder) / "python"
    await environments.ensure("ledger", str(python))
    assert python.exists()
    shutil.rmtree(folder / ".venv")
    await environments.ensure("ledger", str(python))
    assert python.exists()


async def test_commands_outside_the_environment_are_left_alone(tmp_path):
    environments = Environments(lambda name: tmp_path / name)
    await environments.ensure("ledger", "/usr/bin/true")
    assert not (tmp_path / "ledger").exists()


async def test_an_environment_that_cant_be_built_says_why(tmp_path):
    (tmp_path / "ledger").mkdir()
    environments = Environments(lambda name: tmp_path / name)
    with pytest.raises(McpServerError, match="Couldn't install what ledger needs"):
        await environments.ensure("ledger", str(environment.scripts(tmp_path / "ledger") / "ledger-mcp"))


async def test_a_process_that_cant_be_got_ready_is_tried_again_and_not_started(tmp_path):
    attempts: list[int] = []
    stop = asyncio.Event()

    async def prepare() -> None:
        attempts.append(1)
        stop.set()
        raise McpServerError("no uv")

    spec = ProcessSpec("/nonexistent", [], {}, None)
    await asyncio.wait_for(keep_running("test", lambda: spec, stop, logging.getLogger("test"), prepare=prepare), 5)
    assert attempts == [1]
