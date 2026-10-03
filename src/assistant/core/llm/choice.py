"""Which model the assistant uses: the provider, its key, and the main and worker models.

Set in the app (Settings → Model, /model), it's saved in the Store and overrides .env. Without it,
the settings from .env apply. The key is kept encrypted apart from the rest (core/secret_store.py)
and never leaves the daemon: clients only learn whether one is set.
"""

from dataclasses import asdict, dataclass, replace

from langgraph.store.base import BaseStore

from assistant.core import secret_store
from assistant.core.config import settings
from assistant.core.secret_store import SecretBox, SecretError

_NAMESPACE = ("settings",)
_KEY = "model"
_SECRET = "model:api_key"


@dataclass(frozen=True)
class ModelChoice:
    provider: str
    # The Anthropic or OpenAI API key, or the GitHub token for Copilot. Empty: the provider's SDK
    # reads its usual environment variable.
    api_key: str
    # OpenAI-compatible servers other than OpenAI (Ollama, others). Empty for the provider's own.
    base_url: str
    model: str
    worker_model: str


@dataclass(frozen=True)
class ModelProvider:
    """A provider clients offer, with the models to suggest."""

    id: str
    name: str
    key_label: str
    key_help: str
    model: str
    worker_model: str
    # OpenAI-compatible: the server's URL can be given.
    takes_base_url: bool = False


PROVIDERS = [
    ModelProvider(
        "anthropic",
        "Anthropic",
        "API key",
        "Create one at https://console.anthropic.com/settings/keys.",
        "claude-opus-5-5",
        "claude-sonnet-5-5",
    ),
    ModelProvider(
        "copilot",
        "GitHub Copilot",
        "GitHub token",
        "A GitHub token of an account with a Copilot subscription. Copilot's model ids use dots.",
        "claude-opus-5.5",
        "claude-sonnet-5.5",
    ),
    ModelProvider(
        "openai",
        "OpenAI-compatible",
        "API key",
        "OpenAI, or another server that speaks its API (for Ollama, any text as the key).",
        "",
        "",
        takes_base_url=True,
    ),
]


def provider(provider_id: str) -> ModelProvider | None:
    return next((p for p in PROVIDERS if p.id == provider_id), None)


async def saved(store: BaseStore, box: SecretBox) -> ModelChoice | None:
    """The choice made in the app, if any. A key that can't be read any more (the key file
    changed) comes back empty, so the app asks for it again."""
    item = await store.aget(_NAMESPACE, _KEY)
    if item is None:
        return None
    try:
        key = await secret_store.get(store, box, _SECRET)
    except SecretError:
        key = ""
    return ModelChoice(**{**item.value, "api_key": key})


async def save(store: BaseStore, box: SecretBox, choice: ModelChoice) -> None:
    await store.aput(_NAMESPACE, _KEY, asdict(replace(choice, api_key="")))
    if choice.api_key:
        await secret_store.put(store, box, _SECRET, choice.api_key)
    else:
        await secret_store.delete(store, _SECRET)


async def clear(store: BaseStore) -> None:
    await store.adelete(_NAMESPACE, _KEY)
    await secret_store.delete(store, _SECRET)


async def current(store: BaseStore, box: SecretBox) -> ModelChoice:
    """The app's choice, or .env's."""
    return await saved(store, box) or from_env()


async def migrate(store: BaseStore, box: SecretBox) -> None:
    """Moves a key saved in plain text, before keys were encrypted, into the secret store."""
    item = await store.aget(_NAMESPACE, _KEY)
    if item is not None and item.value.get("api_key"):
        await save(store, box, ModelChoice(**item.value))


def from_env() -> ModelChoice:
    keys = {
        "anthropic": settings.anthropic_api_key,
        "openai": settings.openai_api_key,
        "copilot": settings.copilot_github_token,
    }
    base_url = settings.openai_base_url if settings.provider == "openai" else ""
    return ModelChoice(settings.provider, keys[settings.provider], base_url, settings.model, settings.worker_model)
