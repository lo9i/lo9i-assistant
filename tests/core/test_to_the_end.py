"""Work that must finish once started is waited for through any cancellation of its caller."""

import asyncio

import pytest

from assistant.core.to_the_end import to_the_end


async def test_work_finishes_before_a_caller_cancelled_twice_is_cancelled():
    release = asyncio.Event()
    done: list[str] = []

    async def write() -> str:
        await release.wait()
        done.append("written")
        return "written"

    caller = asyncio.create_task(to_the_end(write()))
    await asyncio.sleep(0)
    caller.cancel()
    await asyncio.sleep(0)
    caller.cancel()
    await asyncio.sleep(0)
    assert not caller.done()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await caller
    assert done == ["written"]


async def test_its_result_and_errors_come_back_when_nothing_cancels():
    async def fail() -> None:
        raise ValueError("no")

    async def answer() -> int:
        return 42

    assert await to_the_end(answer()) == 42
    with pytest.raises(ValueError):
        await to_the_end(fail())
