"""Waiting on several things at once."""

import asyncio
from collections.abc import Awaitable
from typing import Any


async def first(*waits: Awaitable[object]) -> None:
    """Returns when the first of `waits` finishes, and ends the others."""
    tasks = [asyncio.ensure_future(w) for w in waits]
    try:
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    finally:
        await given_up(*tasks)


async def given_up(*tasks: asyncio.Future[Any]) -> None:
    """Cancels those of `tasks` still pending and waits for them to end. A task left pending is destroyed with what
    it waits on (a queue nothing else holds), which asyncio logs as "Task was destroyed but it is pending!"."""
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
