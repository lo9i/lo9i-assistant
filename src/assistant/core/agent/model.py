"""The model from any client: which provider, key and models the assistant uses. Set in the app, it
overrides .env and applies at once: the graph, digester and titler are rebuilt, and runs already
going finish on the model they started with. The key never leaves the daemon."""

import asyncio
from dataclasses import dataclass

from langchain_core.messages import HumanMessage

from assistant.core.agent.base import ServiceBase
from assistant.core.conversation.digest import build_digester
from assistant.core.conversation.titles import build_titler
from assistant.core.graph import build_graph
from assistant.core.llm import build_llm, choice
from assistant.core.llm.choice import ModelChoice, ModelProvider

__all__ = ["ModelMixin", "ModelProvider", "ModelSettingsError", "ModelStatus"]

_CHECK_SECONDS = 60


class ModelSettingsError(Exception):
    """The settings are incomplete, or a model didn't answer with them. The text says which."""


@dataclass
class ModelStatus:
    """What a client shows. Says whether a key is set, never the key."""

    # app: set in the app. env: from .env.
    source: str
    provider: str
    base_url: str
    model: str
    worker_model: str
    key_set: bool


class ModelMixin(ServiceBase):
    _model: ModelChoice

    def model_providers(self) -> list[ModelProvider]:
        return list(choice.PROVIDERS)

    async def model_status(self) -> ModelStatus:
        return _status(self._model, await choice.saved(self._storage.store, self.secrets) is not None)

    async def set_model(self, provider: str, api_key: str, base_url: str, model: str, worker_model: str) -> ModelStatus:
        """Check that both models answer, then save and use them. An empty key keeps the current
        one when the provider stays the same. Raises ModelSettingsError."""
        new = self._new_choice(provider, api_key.strip(), base_url.strip(), model.strip(), worker_model.strip())
        await _check(new)
        await choice.save(self._storage.store, self.secrets, new)
        self._use_model(new)
        return _status(new, saved=True)

    async def reset_model(self) -> ModelStatus:
        """Forget the app's choice and use .env's again."""
        await choice.clear(self._storage.store)
        self._use_model(choice.from_env())
        return _status(self._model, saved=False)

    def _use_model(self, model: ModelChoice) -> None:
        self._model = model
        self._digester = build_digester(model)
        self._titler = build_titler(model)
        self._graph = build_graph(self._storage, model, self._digester, self.mcp)

    def _new_choice(self, provider: str, api_key: str, base_url: str, model: str, worker_model: str) -> ModelChoice:
        known = choice.provider(provider)
        if known is None:
            raise ModelSettingsError(f"Unknown provider {provider}.")
        key = api_key or (self._model.api_key if self._model.provider == provider else "")
        if not key:
            raise ModelSettingsError(f"Enter the {known.key_label}.")
        if not model or not worker_model:
            raise ModelSettingsError("Enter both models: the main one and the worker.")
        url = base_url if known.takes_base_url else ""
        return ModelChoice(provider, key, url, model, worker_model)


async def _check(new: ModelChoice) -> None:
    """One short request to each model, so a wrong key or model id is caught before it's used."""
    for model in dict.fromkeys([new.model, new.worker_model]):
        try:
            async with asyncio.timeout(_CHECK_SECONDS):
                await build_llm(new, model).ainvoke([HumanMessage("Reply with OK.")])
        except Exception as e:
            raise ModelSettingsError(f"{model} didn't answer: {_reason(e)}") from e


def _reason(error: Exception) -> str:
    text = str(error).strip() or type(error).__name__
    return text if len(text) <= 300 else text[:300] + "…"


def _status(model: ModelChoice, saved: bool) -> ModelStatus:
    return ModelStatus(
        source="app" if saved else "env",
        provider=model.provider,
        base_url=model.base_url,
        model=model.model,
        worker_model=model.worker_model,
        key_set=bool(model.api_key),
    )
