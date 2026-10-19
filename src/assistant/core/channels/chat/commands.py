"""The commands a channel offers (Telegram's command menu, Slack's slash commands): /new, and each
installed agent's command, which hands the channel's conversation to it (/claude <folder>, /claude off).
The daemon sends them in the stream's `hello`, and again as `commands` when they change."""

from collections.abc import Sequence

from assistant.core.conversation.handoffs import Agent

FIXED = [{"command": "new", "description": "Start a new conversation with your next message"}]


def listed(agents: Sequence[Agent]) -> list[dict[str, str]]:
    return [*FIXED, *({"command": a.command, "description": _description(a)} for a in agents)]


def _description(agent: Agent) -> str:
    return f"Hand this conversation to {agent.name}: /{agent.command} <folder>, /{agent.command} off"
