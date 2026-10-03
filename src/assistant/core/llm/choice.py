"""Which model the assistant uses: the provider, the values it asks for (core/llm/providers.py), and
the main and worker models.

Set in the app (Settings → Model, /model), it's saved in the Store and overrides .env. Without it,
the settings from .env apply. Secret values (keys, tokens) are kept encrypted apart from the rest
(core/secret_store.py) and never leave the daemon: clients only learn which are set.
"""

import json
from dataclasses import dataclass, field

from langgraph.store.base import BaseStore

from assistant.core import secret_store
from assistant.core.config import settings
from assistant.core.llm.providers import PROVIDERS, ModelProvider, provider
from assistant.core.secret_store import SecretBox, SecretError

__all__ = ["PROVIDERS", "ModelChoice", "ModelProvider", "provider"]

_NAMESPACE = ("settings",)
_KEY = "model"
_SECRETS = "model:secrets"
# Before providers had their own fields: the one key, alone.
_OLD_KEY = "model:api_key"


@dataclass(frozen=True)
class ModelChoice:
    provider: str
    model: str
    worker_model: str
    # The provider's fields by key, secret ones included. An empty or missing value: the
    # provider's SDK reads its usual environment variable, if it has one.
    values: dict[str, str] = field(default_factory=dict)


async def saved(store: BaseStore, box: SecretBox) -> ModelChoice | None:
    """The choice made in the app, if any. Secrets that can't be read any more (the key file
    changed) come back empty, so the app asks for them again."""
    item = await store.aget(_NAMESPACE, _KEY)
    if item is None:
        return None
    record = item.value
    values = {**record.get("values", {}), **await _secrets(store, box)}
    return ModelChoice(record["provider"], record["model"], record["worker_model"], values)


async def save(store: BaseStore, box: SecretBox, choice: ModelChoice) -> None:
    secret = _secret_keys(choice.provider)
    plain = {k: v for k, v in choice.values.items() if k not in secret}
    hidden = {k: v for k, v in choice.values.items() if k in secret and v}
    record = {"provider": choice.provider, "model": choice.model, "worker_model": choice.worker_model, "values": plain}
    await store.aput(_NAMESPACE, _KEY, record)
    await secret_store.put(store, box, _SECRETS, json.dumps(hidden))
    await secret_store.delete(store, _OLD_KEY)


async def clear(store: BaseStore) -> None:
    await store.adelete(_NAMESPACE, _KEY)
    await secret_store.delete(store, _SECRETS)
    await secret_store.delete(store, _OLD_KEY)


async def current(store: BaseStore, box: SecretBox) -> ModelChoice:
    """The app's choice, or .env's."""
    return await saved(store, box) or from_env()


async def migrate(store: BaseStore, box: SecretBox) -> None:
    """Moves a choice saved before providers had their own fields (one key, maybe a server URL,
    perhaps in plain text) to the current form."""
    item = await store.aget(_NAMESPACE, _KEY)
    if item is None or "values" in item.value:
        return
    old = item.value
    key = old.get("api_key") or await _old_key(store, box)
    values = {k: v for k, v in {"api_key": key, "base_url": old.get("base_url", "")}.items() if v}
    await save(store, box, ModelChoice(old["provider"], old["model"], old["worker_model"], values))


def from_env() -> ModelChoice:
    keys = {
        "anthropic": settings.anthropic_api_key,
        "openai": settings.openai_api_key,
        "copilot": settings.copilot_github_token,
    }
    values = {"api_key": keys[settings.provider]}
    if settings.provider == "openai" and settings.openai_base_url:
        values["base_url"] = settings.openai_base_url
    return ModelChoice(settings.provider, settings.model, settings.worker_model, values)


def secret_keys(choice: ModelChoice) -> set[str]:
    """The choice's values that are secret."""
    return _secret_keys(choice.provider)


def _secret_keys(provider_id: str) -> set[str]:
    known = provider(provider_id)
    return {f.key for f in known.fields if f.secret} if known else set()


async def _secrets(store: BaseStore, box: SecretBox) -> dict[str, str]:
    try:
        text = await secret_store.get(store, box, _SECRETS)
    except SecretError:
        return {}
    return json.loads(text) if text else {}


async def _old_key(store: BaseStore, box: SecretBox) -> str:
    try:
        return await secret_store.get(store, box, _OLD_KEY)
    except SecretError:
        return ""
