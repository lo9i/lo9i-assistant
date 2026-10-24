"""Cancelling a run: the graph stops, a running command is killed, and the conversation can go on."""

import asyncio
import os

from langchain_core.messages import ToolMessage

from assistant.core.events import Cancelled
from tests.conftest import collect, written


async def _gone(pid: int) -> bool:
    for _ in range(200):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        await asyncio.sleep(0.05)
    return False


async def test_cancel_kills_a_running_command_and_answers_its_call(service, script, tmp_path):
    script.call("bash", command="sleep 30 & echo $! > pid; wait").reply("fine")
    session = await service.session("owner", "cli")
    run = asyncio.create_task(collect(service.send(session, "wait a bit")))
    sleeper = int(await written(tmp_path / "workspace" / "pid"))
    assert await service.cancel(session.thread_id)
    events = await asyncio.wait_for(run, 10)
    assert isinstance(events[-1], Cancelled) and await _gone(sleeper)
    assert not await service.cancel(session.thread_id)
    await collect(service.send(session, "and now?"))
    results = [m for m in script.requests[-1] if isinstance(m, ToolMessage)]
    assert results[-1].text == "[cancelled by the user before it finished]"


async def test_every_run_in_progress_is_cancelled_at_once_so_a_restart_waiting_for_them_goes_ahead(
    service, script, tmp_path
):
    script.call("bash", command="echo started > mark; sleep 30")
    session = await service.session("owner", "cli")
    run = asyncio.create_task(collect(service.send(session, "wait")))
    await written(tmp_path / "workspace" / "mark")
    assert service.runs_in_progress() == 1
    assert service.cancel_runs() == 1
    assert isinstance((await asyncio.wait_for(run, 10))[-1], Cancelled)
    await asyncio.wait_for(service.until_no_runs(), 1)
    assert service.cancel_runs() == 0
