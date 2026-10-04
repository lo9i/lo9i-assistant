"""Chat channels installed as plugins (Telegram, Slack), for the apps: whether each one's process is
connected, what it shows for setting it up, and its buttons."""

from dataclasses import dataclass

from assistant.core.agent.base import ServiceBase
from assistant.core.channels.hub import ChannelNotConnectedError, SetupItem
from assistant.core.mcp import servers

__all__ = ["ChannelNotConnectedError", "ChannelStatus", "ChannelsMixin", "SetupItem"]


@dataclass
class ChannelStatus:
    name: str
    enabled: bool
    # Its process holds its stream open: it can chat, take send_message and job approvals.
    connected: bool
    items: list[SetupItem]


class ChannelsMixin(ServiceBase):
    async def channels(self) -> list[ChannelStatus]:
        return [
            ChannelStatus(s.name, s.enabled, self.channels_hub.connected(s.name), self.channels_hub.items(s.name))
            for s in await servers.load_all(self._storage.store)
            if s.channel_command
        ]

    async def channel_names(self) -> list[str]:
        """The installed channels, connected or not."""
        return [c.name for c in await self.channels()]

    def press_channel_action(self, name: str, action: str) -> None:
        """A setup button pressed in an app. Raises ChannelNotConnectedError."""
        self.channels_hub.act(name, action)
