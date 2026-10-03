"""The model from any client: which provider, its values (keys, URLs) and models the assistant
uses. Set in the app, it overrides .env and applies at once: the graph, digester and titler are
rebuilt, and runs already going finish on the model they started with. A provider's package is
installed the first time it's chosen. Secret values never leave the daemon."""

import asyncio
import logging
from dataclasses import dataclass, replace

from langchain_core.messages import HumanMessage
from langgraph.store.base import BaseStore

from assistant.core.agent.base import ServiceBase
from assistant.core.conversation.digest import build_digester
from assistant.core.conversation.titles import build_titler
from assistant.core.graph import build_graph
from assistant.core.llm import build_llm, choice, packages
from assistant.core.llm.choice import ModelChoice
from assistant.core.llm.packages import PackageError
from assistant.core.llm.providers import PROVIDERS, ModelProvider, ProviderField, provider
from assistant.core.secret_store import SecretBox
from assistant.core.usage.meter import TokenMeter

__all__ = ["ModelMixin", "ModelProvider", "ModelSettingsError", "ModelStatus", "ProviderField", "usable_choice"]

logger = logging.getLogger(__name__)

_CHECK_SECONDS = 60


class ModelSettingsError(Exception):
    """The settings are incomplete, or a model didn't answer with them. The text says which."""


@dataclass
class ModelStatus:
    """What a client shows. Says which secret values are set, never the values."""

    # app: set in the app. env: from .env.
    source: str
    provider: str
    model: str
    worker_model: str
    # The values that aren't secret, like a server URL.
    values: dict[str, str]
    # The secret values that are set, by key.
    secrets_set: list[str]


class ModelMixin(ServiceBase):
    _model: ModelChoice

    def model_providers(self) -> list[ModelProvider]:
        """Every provider, saying whether its package is installed yet."""
        return [replace(p, installed=packages.installed(p)) for p in PROVIDERS]

    async def model_status(self) -> ModelStatus:
        return _status(self._model, await choice.saved(self._storage.store, self.secrets) is not None)

    async def set_model(self, provider_id: str, values: dict[str, str], model: str, worker_model: str) -> ModelStatus:
        """Install the provider's package if needed, check that both models answer, then save and
        use them. An empty secret keeps the current one when the provider stays the same. Raises
        ModelSettingsError."""
        known = provider(provider_id)
        if known is None:
            raise ModelSettingsError(f"Unknown provider {provider_id}.")
        new = ModelChoice(known.id, model.strip(), worker_model.strip(), self._values(known, values))
        _check_complete(known, new)
        try:
            await packages.ensure(known)
        except PackageError as e:
            raise ModelSettingsError(str(e)) from e
        await _check(new, TokenMeter(self._storage.usage, "check"))
        await choice.save(self._storage.store, self.secrets, new)
        self._use_model(new)
        return _status(new, saved=True)

    def _values(self, known: ModelProvider, given: dict[str, str]) -> dict[str, str]:
        """The provider's fields from what was given; a secret left empty keeps the saved one."""
        same = self._model.provider == known.id
        values = {}
        for f in known.fields:
            value = given.get(f.key, "").strip()
            if not value and f.secret and same:
                value = self._model.values.get(f.key, "")
            if value:
                values[f.key] = value
        return values

    async def reset_model(self) -> ModelStatus:
        """Forget the app's choice and use .env's again."""
        await choice.clear(self._storage.store)
        self._use_model(choice.from_env())
        return _status(self._model, saved=False)

    def _use_model(self, model: ModelChoice) -> None:
        self._model = model
        self._digester = build_digester(model, self._storage.usage)
        self._titler = build_titler(model, self._storage.usage)
        self._graph = build_graph(self._storage, model, self._digester, self.mcp)


async def usable_choice(store: BaseStore, secrets: SecretBox) -> ModelChoice:
    """The model to start with: the saved choice, its package installed again if it went missing (a
    reinstall), or .env's if that fails."""
    current = await choice.current(store, secrets)
    known = provider(current.provider)
    if known is None:
        return choice.from_env()
    try:
        await packages.ensure(known)
    except PackageError as e:
        logger.error("Can't use %s (%s); using the model from .env until it's fixed in the app.", known.name, e)
        return choice.from_env()
    return current


def _check_complete(known: ModelProvider, new: ModelChoice) -> None:
    missing = next((f for f in known.fields if f.required and not new.values.get(f.key)), None)
    if missing is not None:
        raise ModelSettingsError(f"Enter the {missing.label}.")
    if not new.model or not new.worker_model:
        raise ModelSettingsError("Enter both models: the main one and the worker.")


async def _check(new: ModelChoice, meter: TokenMeter) -> None:
    """One short request to each model, so a wrong key or model id is caught before it's used."""
    for model in dict.fromkeys([new.model, new.worker_model]):
        try:
            async with asyncio.timeout(_CHECK_SECONDS):
                await build_llm(new, model).ainvoke([HumanMessage("Reply with OK.")], config={"callbacks": [meter]})
        except Exception as e:
            raise ModelSettingsError(f"{model} didn't answer: {_reason(e)}") from e


def _reason(error: Exception) -> str:
    text = str(error).strip() or type(error).__name__
    return text if len(text) <= 300 else text[:300] + "…"


def _status(model: ModelChoice, saved: bool) -> ModelStatus:
    secret = choice.secret_keys(model)
    return ModelStatus(
        source="app" if saved else "env",
        provider=model.provider,
        model=model.model,
        worker_model=model.worker_model,
        values={k: v for k, v in model.values.items() if k not in secret},
        secrets_set=sorted(k for k in model.values if k in secret and model.values[k]),
    )
