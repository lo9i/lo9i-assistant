"""The voice model's tool calls, logged by their call id: a call it makes again, or that reaches the daemon twice,
gets the first one's result instead of asking the assistant again (an action done twice, a second run in the
conversation). Results are kept in the Store, the latest KEPT; a call still being answered is waited for."""

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from langgraph.store.base import BaseStore

_NAMESPACE = ("voice_tool_calls",)
KEPT = 200
# More than are ever kept, to read them all when pruning.
_READ = 10_000


class ToolCalls:
    def __init__(self, store: BaseStore) -> None:
        self._store = store
        # The calls being answered, by id.
        self._answering: dict[str, asyncio.Future[str]] = {}

    async def answer(self, call_id: str, ask: Callable[[], Awaitable[str]]) -> str:
        """The result of the call `call_id`: the logged one, the one being worked out, or `ask`'s, logged. One that
        fails isn't logged: the call made again asks again."""
        logged = await self._store.aget(_NAMESPACE, call_id)
        if logged is not None:
            return logged.value["result"]
        # Checked after the Store with nothing awaited before the future is set: a second call waits for this one.
        if (answering := self._answering.get(call_id)) is not None:
            return await asyncio.shield(answering)
        answering = asyncio.get_running_loop().create_future()
        self._answering[call_id] = answering
        try:
            result = await ask()
            await self._log(call_id, result)
        except BaseException as e:
            _fail(answering, e)
            raise
        finally:
            self._answering.pop(call_id, None)
        answering.set_result(result)
        return result

    async def _log(self, call_id: str, result: str) -> None:
        await self._store.aput(_NAMESPACE, call_id, {"result": result, "at": datetime.now(UTC).isoformat()})
        logged = await self._store.asearch(_NAMESPACE, limit=_READ)
        for old in sorted(logged, key=lambda item: item.value["at"], reverse=True)[KEPT:]:
            await self._store.adelete(_NAMESPACE, old.key)


def _fail(answering: asyncio.Future[str], error: BaseException) -> None:
    """Whoever waits for the same call learns how it ended. Nobody may be waiting: the error is marked as seen."""
    if isinstance(error, asyncio.CancelledError):
        answering.cancel()
        return
    answering.set_exception(error)
    answering.exception()
