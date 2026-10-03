"""Waiting on several things at once."""

import asyncio
from collections.abc import Awaitable


async def first(*waits: Awaitable[object]) -> None:
    """Returns when the first of `waits` finishes, and cancels the others."""
    tasks = [asyncio.ensure_future(w) for w in waits]
    try:
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for task in tasks:
            task.cancel()
