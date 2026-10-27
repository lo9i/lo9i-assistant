"""How many tokens a model takes in, its context window, which a conversation's context is measured against (the
context bar, core/agent/usage.py; the doctor, core/doctor/context.py). Only measured: compaction still starts at
EPOCH_MAX_TOKENS (core/conversation/epochs.py). The provider says where it lists its models with their windows
(Anthropic, Copilot); for the others it isn't known, and the measure is EPOCH_MAX_TOKENS.

Learned once per model, when it's saved in the app or first measured, and kept in the Store; a provider that
couldn't say isn't asked again until the daemon restarts."""

import logging
from collections.abc import Awaitable, Callable

import anthropic
from langgraph.store.base import BaseStore

from assistant.core.config import settings
from assistant.core.llm import copilot
from assistant.core.llm.choice import ModelChoice

logger = logging.getLogger(__name__)

_NAMESPACE = ("model_windows",)


async def _anthropic(choice: ModelChoice, model: str) -> int | None:
    async with anthropic.AsyncAnthropic(api_key=choice.values.get("api_key") or None) as client:
        return (await client.models.retrieve(model)).max_input_tokens


async def _copilot(choice: ModelChoice, model: str) -> int | None:
    return await copilot.context_window(choice.values.get("api_key", ""), model)


_LOOKUPS: dict[str, Callable[[ModelChoice, str], Awaitable[int | None]]] = {
    "anthropic": _anthropic,
    "copilot": _copilot,
}


class ContextWindows:
    def __init__(self, store: BaseStore) -> None:
        self._store = store
        # Models whose provider couldn't say, not asked again.
        self._unknown: set[str] = set()

    async def of(self, choice: ModelChoice) -> int:
        """The main model's window, or EPOCH_MAX_TOKENS when it isn't known."""
        return await self._known(choice) or settings.epoch_max_tokens

    async def _known(self, choice: ModelChoice) -> int | None:
        key = f"{choice.provider}:{choice.model}"
        kept = await self._store.aget(_NAMESPACE, key)
        if kept is not None:
            return int(kept.value["tokens"])
        if key in self._unknown or choice.provider not in _LOOKUPS:
            return None
        tokens = await self._asked(choice)
        if tokens:
            await self._store.aput(_NAMESPACE, key, {"tokens": tokens})
        else:
            self._unknown.add(key)
        return tokens

    async def _asked(self, choice: ModelChoice) -> int | None:
        try:
            return await _LOOKUPS[choice.provider](choice, choice.model)
        except (anthropic.APIError, copilot.CopilotAuthError) as e:
            # A refused key, no network or an unknown model leaves it unknown, as for a provider that doesn't say.
            logger.info("Couldn't learn the context window of %s: %s", choice.model, e)
            return None
