"""Connecting Slack from any client, and the settings the Slack adapter runs with. Tokens never leave
the daemon."""

from dataclasses import dataclass

from assistant.core import identity
from assistant.core.agent.base import ServiceBase
from assistant.core.integrations.slack import connection
from assistant.core.integrations.slack.connection import SlackConfig, SlackError

__all__ = ["SlackConfig", "SlackError", "SlackMixin", "SlackStatus"]

# The outbox channel the Slack adapter registers while it's connected.
_CHANNEL = "slack"


@dataclass
class SlackStatus:
    """What a setup screen shows. Never includes the tokens."""

    connected: bool
    running: bool
    team: str
    owner_name: str


class SlackMixin(ServiceBase):
    async def slack_status(self) -> SlackStatus:
        return self._slack_status(await connection.load(self._storage.store))

    async def slack_manifest(self) -> str:
        """The app manifest for Slack, named after the assistant."""
        return connection.manifest(await identity.load_name(self._storage.store))

    async def connect_slack(self, app_token: str, bot_token: str, user_token: str) -> SlackStatus:
        """Check the tokens with Slack, then save. Raises SlackError."""
        config = await connection.verify(app_token, bot_token, user_token)
        await connection.save(self._storage.store, config)
        return self._slack_status(config)

    async def disconnect_slack(self) -> None:
        await connection.clear(self._storage.store)

    # Used by the Slack adapter.

    async def slack_config(self) -> SlackConfig:
        return await connection.load(self._storage.store)

    def _slack_status(self, config: SlackConfig) -> SlackStatus:
        running = _CHANNEL in self.outbox.channels
        return SlackStatus(config.connected, running, config.team, config.owner_name)
