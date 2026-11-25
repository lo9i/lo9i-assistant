"""The security audit for clients (core/security_audit/): the local parts, read as the daemon runs them, and those
that read its state: paired devices, the setup code, and what plugins run here."""

import asyncio
from datetime import UTC, datetime
from pathlib import Path

from lo9i.core import devices, setup_code
from lo9i.core.agent.base import ServiceBase
from lo9i.core.config import settings
from lo9i.core.mcp import servers
from lo9i.core.security_audit import local, service
from lo9i.core.setup_check import SetupCheck, SetupReport


class SecurityAuditMixin(ServiceBase):
    async def security_audit(self) -> SetupReport:
        found, state = await asyncio.gather(asyncio.to_thread(local.checks), self._audited_state())
        return SetupReport([*found, *state])

    async def _audited_state(self) -> list[SetupCheck]:
        return [*await self._audited_devices(), *await self._audited_plugins()]

    async def _audited_devices(self) -> list[SetupCheck]:
        store, now = self._storage.store, datetime.now(UTC)
        paired = await devices.list_all(store)
        listed = [service.device(d, now) for d in paired] or [service.no_devices()]
        code_open = await setup_code.available(store, Path(settings.setup_code_path).expanduser())
        code = service.setup_code(code_open, settings.https_port > 0)
        return listed if code is None else [*listed, code]

    async def _audited_plugins(self) -> list[SetupCheck]:
        installed = await servers.load_all(self._storage.store)
        return [service.plugin(s) for s in installed if service.runs_here(s)]
