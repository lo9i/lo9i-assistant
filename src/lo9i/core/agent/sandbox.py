"""The bash sandbox's setting (core/sandbox/), from any client: Settings → General → Sandbox, /sandbox."""

from lo9i.core.agent.base import ServiceBase
from lo9i.core.sandbox import setting
from lo9i.core.sandbox.status import SandboxStatus, SandboxUnavailableError, ready, status

__all__ = ["SandboxMixin", "SandboxStatus", "SandboxUnavailableError"]


class SandboxMixin(ServiceBase):
    async def sandbox_status(self) -> SandboxStatus:
        return await status(self._storage.store)

    async def set_sandbox(self, enabled: bool) -> SandboxStatus:
        """Raises SandboxUnavailableError when it's turned on without a runtime that answers or its image."""
        if enabled:
            await ready()
        await setting.enable(self._storage.store, enabled)
        return await self.sandbox_status()
