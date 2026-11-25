import httpx

from lo9i.client.daemon_client.transport import Transport
from lo9i.core.agent import (
    BackupModelStatus,
    ModelOption,
    ModelProvider,
    ModelSettingsError,
    ModelStatus,
    ProviderField,
)
from lo9i.core.conversation.dispatch_setting import DispatchSetting, DispatchSettingError

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

    async def backups(self) -> list[BackupModelStatus]:
        """The backup models, in the order they're tried when the model fails on the provider's side."""
        return _backups(await self._transport.request("GET", f"{_PATH}/backups"))

    async def add_backup(self, provider: str, values: dict[str, str], model: str) -> list[BackupModelStatus]:
        """Adds it last once it answers; on the main model's provider, values left empty take the main model's.
        Raises ModelSettingsError."""
        body = {"provider": provider, "values": values, "model": model}
        data = await self._transport.request(
            "POST", f"{_PATH}/backups", json=body, errors={400: ModelSettingsError}, timeout=_CHECK_TIMEOUT
        )
        return _backups(data)

    async def order_backups(self, ids: list[str]) -> list[BackupModelStatus]:
        """Raises ModelSettingsError for an id that isn't a backup."""
        body = {"ids": ids}
        data = await self._transport.request(
            "PUT", f"{_PATH}/backups/order", json=body, errors={400: ModelSettingsError}
        )
        return _backups(data)

    async def remove_backup(self, backup_id: str) -> list[BackupModelStatus]:
        return _backups(await self._transport.request("DELETE", f"{_PATH}/backups/{backup_id}"))

    async def dispatch(self) -> DispatchSetting:
        """How sure routing a message from the inbox has to be to continue a conversation."""
        return DispatchSetting(**await self._transport.request("GET", "/settings/dispatch"))

    async def set_dispatch(self, setting: DispatchSetting) -> DispatchSetting:
        """Raises DispatchSettingError."""
        body = {"confidence": setting.confidence}
        data = await self._transport.request("PUT", "/settings/dispatch", json=body, errors={400: DispatchSettingError})
        return DispatchSetting(**data)


def _backups(data: list[dict]) -> list[BackupModelStatus]:
    return [BackupModelStatus(**b) for b in data]
