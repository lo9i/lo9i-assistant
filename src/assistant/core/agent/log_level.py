"""The level the daemon records its log at, from any client (Settings → Logs)."""

from assistant.core.agent.base import ServiceBase
from assistant.core.logs import LogLevel, level


class LogLevelMixin(ServiceBase):
    async def log_level(self) -> LogLevel:
        return await level.load(self._storage.store)

    async def set_log_level(self, chosen: str) -> LogLevel:
        """Stored and applied at once. Raises LogLevelError."""
        return await level.save(self._storage.store, chosen)

    async def apply_log_level(self) -> None:
        """The saved level, when the daemon starts."""
        level.apply(await self.log_level())
