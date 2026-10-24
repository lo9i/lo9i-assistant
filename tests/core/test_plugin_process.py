"""A plugin's process (core/mcp/process.py), kept running until it's stopped."""

import asyncio
import errno
import os
import sys

import pytest

from assistant.core.mcp import process


@pytest.mark.parametrize("gone", [ProcessLookupError(errno.ESRCH, "No such process"), PermissionError(errno.EPERM, "")])
async def test_stopping_a_process_that_just_exited_and_isnt_reaped_yet_is_no_error(monkeypatch, gone):
    """Stopped as it exits, its returncode is still None until its exit is handled: its group is then gone
    (ESRCH) or, on macOS, only a zombie, which kill answers with EPERM. Nothing is left to stop either way."""
    proc = await asyncio.create_subprocess_exec(sys.executable, "-c", "pass", start_new_session=True)

    def exited(pid: int, sig: int) -> None:
        raise gone

    monkeypatch.setattr(os, "killpg", exited)
    await asyncio.wait_for(process._terminate(proc), 5)
    assert proc.returncode == 0
