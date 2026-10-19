import httpx

from assistant.client.daemon_client.transport import Transport
from assistant.core.agent import ModelOption, ModelProvider, ModelSettingsError, ModelStatus, ProviderField
from assistant.core.conversation.dispatch_setting import DispatchSetting, DispatchSettingError

_PATH = "/settings/model"
# Saving may install the provider's package (up to 10 minutes) and asks each model to answer once.
_CHECK_TIMEOUT = httpx.Timeout(800)


class ModelApi:
    """The model the assistant uses: its provider, the values it asks for, and the models. Set here,
    it overrides .env."""

    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    async def providers(self) -> list[ModelProvider]:
        data = await self._transport.request("GET", f"{_PATH}/providers")
        return [ModelProvider(**{**p, "fields": [ProviderField(**f) for f in p["fields"]]}) for p in data]

    async def status(self) -> ModelStatus:
        return ModelStatus(**await self._transport.request("GET", _PATH))

    async def set(self, provider: str, values: dict[str, str], model: str, worker_model: str) -> ModelStatus:
        """`values` by field key; a secret left empty keeps the saved one when the provider stays the
        same. Installs the provider's package first if needed. Raises ModelSettingsError."""
        body = {"provider": provider, "values": values, "model": model, "worker_model": worker_model}
        data = await self._transport.request(
            "PUT", _PATH, json=body, errors={400: ModelSettingsError}, timeout=_CHECK_TIMEOUT
        )
        return ModelStatus(**data)

    async def available(self, provider: str, values: dict[str, str]) -> list[ModelOption]:
        """The provider's models for these values, to pick from; empty when it can't list them.
        Raises ModelSettingsError."""
        body = {"provider": provider, "values": values}
        data = await self._transport.request("POST", f"{_PATH}/available", json=body, errors={400: ModelSettingsError})
        return [ModelOption(**m) for m in data]

    async def reset(self) -> ModelStatus:
        """Back to the model in .env."""
        return ModelStatus(**await self._transport.request("DELETE", _PATH))

    async def dispatch(self) -> DispatchSetting:
        """How sure routing a message from the inbox has to be to continue a conversation."""
        return DispatchSetting(**await self._transport.request("GET", "/settings/dispatch"))

    async def set_dispatch(self, setting: DispatchSetting) -> DispatchSetting:
        """Raises DispatchSettingError."""
        body = {"confidence": setting.confidence}
        data = await self._transport.request("PUT", "/settings/dispatch", json=body, errors={400: DispatchSettingError})
        return DispatchSetting(**data)
