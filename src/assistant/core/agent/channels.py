"""Chat channels installed as plugins (Telegram, Slack), for the apps: whether each one's process is
connected, what it shows for setting it up, and its buttons."""

from dataclasses import dataclass

from assistant.core import i18n
from assistant.core.agent.base import ServiceBase
from assistant.core.channels.chat import commands
from assistant.core.channels.hub import ChannelNotConnectedError, SetupItem, protocol_problem
from assistant.core.conversation import handoffs
from assistant.core.mcp import servers
from assistant.core.mcp.servers import McpServer

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
            ChannelStatus(s.name, s.enabled, self.channels_hub.connected(s.name), self._items(s))
            for s in await servers.load_all(self._storage.store)
            if s.channel_command
        ]

    async def channel_names(self) -> list[str]:
        """The installed channels, connected or not."""
        return [c.name for c in await self.channels()]

    def _items(self, server: McpServer) -> list[SetupItem]:
        """What its process shows, or why it isn't running: a plugin for another channel protocol."""
        if problem := protocol_problem(server.channel_protocol):
            return [SetupItem("text", "", problem)]
        return self.channels_hub.items(server.name)

    async def channel_commands(self) -> list[dict[str, str]]:
        """What the channels offer: /clear, /pin, /unpin and each agent's command (core/channels/chat/commands.py)."""
        store = self._storage.store
        return commands.listed(await i18n.chosen(store), await handoffs.agents(store))

    def press_channel_action(self, name: str, action: str) -> None:
        """A setup button pressed in an app. Raises ChannelNotConnectedError."""
        self.channels_hub.act(name, action)
