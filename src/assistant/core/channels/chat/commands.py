"""The commands a channel offers (Telegram's command menu, Slack's slash commands): /new, and each
installed agent's command, which hands the channel's conversation to it (/claude <folder>, /claude off).
The daemon sends them in the stream's `hello`, and again as `commands` when they change."""

from collections.abc import Sequence

from assistant.core.conversation.handoffs import Agent
from assistant.core.i18n import Texts


def listed(t: Texts, agents: Sequence[Agent]) -> list[dict[str, str]]:
    new = {"command": "new", "description": t("Start a new conversation with your next message")}
    return [new, *({"command": a.command, "description": _description(t, a)} for a in agents)]


def _description(t: Texts, agent: Agent) -> str:
    return t(
        "Hand this conversation to {agent}: /{command} <folder>, /{command} off",
        agent=agent.name,
        command=agent.command,
    )
