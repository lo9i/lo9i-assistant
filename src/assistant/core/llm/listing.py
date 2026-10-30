"""The models a provider offers the account its values (a key) belong to, so the apps can offer
them to pick from. Only providers with a way to ask list them; for the others the apps take a typed
model id."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from assistant.core.llm import copilot, openrouter


@dataclass(frozen=True)
class ModelOption:
    id: str
    name: str


class ModelListError(Exception):
    """The provider refused the values or couldn't be reached. The text says why."""


async def available(provider_id: str, values: dict[str, str]) -> list[ModelOption]:
    """The provider's models for these values; empty for a provider that can't list them. Raises
    ModelListError."""
    lister = _LISTERS.get(provider_id)
    return await lister(values) if lister else []


async def _copilot(values: dict[str, str]) -> list[ModelOption]:
    if not values.get("api_key"):
        return []  # Nothing to list with until a token is typed.
    try:
        return [ModelOption(id, name) for id, name in await copilot.list_models(values.get("api_key", ""))]
    except copilot.CopilotAuthError as e:
        raise ModelListError(str(e)) from e


async def _openrouter(values: dict[str, str]) -> list[ModelOption]:
    try:
        return [ModelOption(id, name) for id, name in await openrouter.list_models()]
    except openrouter.OpenRouterError as e:
        raise ModelListError(str(e)) from e


_LISTERS: dict[str, Callable[[dict[str, str]], Awaitable[list[ModelOption]]]] = {
    "copilot": _copilot,
    "openrouter": _openrouter,
}
