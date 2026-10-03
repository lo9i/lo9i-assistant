"""Which model the assistant uses: the provider, its key, and the main and worker models.

Set in the app (Settings → Model, /model), it's saved in the Store and overrides .env. Without it,
the settings from .env apply. The key never leaves the daemon: clients only learn whether one is set.
"""

from dataclasses import asdict, dataclass

from langgraph.store.base import BaseStore

from assistant.core.config import settings

_NAMESPACE = ("settings",)
_KEY = "model"


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


async def saved(store: BaseStore) -> ModelChoice | None:
    """The choice made in the app, if any."""
    item = await store.aget(_NAMESPACE, _KEY)
    return ModelChoice(**item.value) if item else None


async def save(store: BaseStore, choice: ModelChoice) -> None:
    await store.aput(_NAMESPACE, _KEY, asdict(choice))


async def clear(store: BaseStore) -> None:
    await store.adelete(_NAMESPACE, _KEY)


async def current(store: BaseStore) -> ModelChoice:
    """The app's choice, or .env's."""
    return await saved(store) or from_env()


def from_env() -> ModelChoice:
    keys = {
        "anthropic": settings.anthropic_api_key,
        "openai": settings.openai_api_key,
        "copilot": settings.copilot_github_token,
    }
    base_url = settings.openai_base_url if settings.provider == "openai" else ""
    return ModelChoice(settings.provider, keys[settings.provider], base_url, settings.model, settings.worker_model)
