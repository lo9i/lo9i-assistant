"""Work that must finish once started, like a write to history, even when the task waiting for it is cancelled:
unlike `asyncio.shield` alone, the waiter waits for it too, so whatever comes after (the run's end, its pruning,
the next run) never overlaps it."""

import asyncio
from collections.abc import Awaitable


async def to_the_end[T](work: Awaitable[T]) -> T:
    """`work`'s result, waited for through any cancellation of the caller, which is passed on once it's done."""
    task = asyncio.ensure_future(work)
    cancelled = False
    while True:
        try:
            result = await asyncio.shield(task)
            break
        except asyncio.CancelledError:
            if task.done():
                raise
            cancelled = True
    if cancelled:
        raise asyncio.CancelledError
    return result


async def settled[T](task: asyncio.Future[T]) -> None:
    """Once `task` is done, however it ended."""
    await asyncio.wait({task})
