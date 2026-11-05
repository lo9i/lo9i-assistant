"""The setup check for clients (core/setup_check/): every part the daemon can check, run when asked. The daemon
answering is checked by answering; the lo9i command against the link install.sh makes, the daemon's PATH not being
the user's shell's."""

import asyncio
from pathlib import Path

from lo9i.core.agent.base import ServiceBase
from lo9i.core.channels.hub import protocol_problem
from lo9i.core.config import settings
from lo9i.core.integrations.email import accounts
from lo9i.core.llm import key_check
from lo9i.core.llm.providers import provider
from lo9i.core.mcp import servers
from lo9i.core.setup_check import SetupCheck, SetupReport, local, service

__all__ = ["SetupCheck", "SetupCheckMixin", "SetupReport"]


class SetupCheckMixin(ServiceBase):
    async def check_setup(self, web_build: Path) -> SetupReport:
        """`web_build`: the folder the daemon serves the web app from."""
        model, others, files = await asyncio.gather(self._model_check(), self._state_checks(), _local(web_build))
        return SetupReport([files[0], model, *others, *files[1:]])

    async def _model_check(self) -> SetupCheck:
        known = provider(self._model.provider)
        if known is None:
            return service.model("", "", "", None)
        missing = next((f.label for f in known.fields if f.required and not self._model.values.get(f.key)), "")
        verdict = None if missing or not self._model.model else await key_check.check(self._model)
        return service.model(known.name, self._model.model, missing, verdict)

    async def _state_checks(self) -> list[SetupCheck]:
        installed = [s for s in await servers.load_all(self._storage.store) if s.enabled]
        plugins = [await self._plugin_check(s.name) for s in installed if s.is_mcp]
        emails = [
            service.email(c.account_id, c.label or c.sender, c.status, c.problem)
            for c in await accounts.list_accounts(self._storage.store)
        ]
        channels = [
            service.channel(s.name, self.channels_hub.connected(s.name), protocol_problem(s.channel_protocol))
            for s in installed
            if s.channel_command
        ]
        return [*plugins, *emails, *channels]

    async def _plugin_check(self, name: str) -> SetupCheck:
        status, error, tools = self.mcp.state(name)
        return service.plugin(name, status, error, len(tools), await self.mcp.health(name))


async def _local(web_build: Path) -> list[SetupCheck]:
    """The daemon first, then the web app, disk space and the command, which read files: in a thread."""
    data = Path(settings.database_path).expanduser().parent
    socket = Path(settings.daemon_socket).expanduser()
    checks = await asyncio.to_thread(lambda: [local.web_app(web_build), local.disk(data), local.command()])
    return [local.daemon(True, socket), *checks]
