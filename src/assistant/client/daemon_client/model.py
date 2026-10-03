import httpx

from assistant.client.daemon_client.transport import Transport
from assistant.core.agent import ModelProvider, ModelSettingsError, ModelStatus

_PATH = "/settings/model"
# Saving asks each model to answer once, which can take a while.
_CHECK_TIMEOUT = httpx.Timeout(150)


class ModelApi:
    """The model the assistant uses: its provider, key and models. Set here, it overrides .env."""

    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    async def providers(self) -> list[ModelProvider]:
        return [ModelProvider(**p) for p in await self._transport.request("GET", f"{_PATH}/providers")]

    async def status(self) -> ModelStatus:
        return ModelStatus(**await self._transport.request("GET", _PATH))

    async def set(self, provider: str, api_key: str, base_url: str, model: str, worker_model: str) -> ModelStatus:
        """An empty key keeps the current one when the provider stays the same. Raises ModelSettingsError."""
        body = {"provider": provider, "api_key": api_key, "base_url": base_url, "model": model}
        body["worker_model"] = worker_model
        data = await self._transport.request(
            "PUT", _PATH, json=body, errors={400: ModelSettingsError}, timeout=_CHECK_TIMEOUT
        )
        return ModelStatus(**data)

    async def reset(self) -> ModelStatus:
        """Back to the model in .env."""
        return ModelStatus(**await self._transport.request("DELETE", _PATH))
