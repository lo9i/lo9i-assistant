"""When the assistant's model asked for its tool calls: kept on its reply, in `response_metadata`, which no model call
sends, so history shows each call with the time it started, as the apps show it live (ToolStarted.at)."""

from datetime import datetime

from langchain_core.messages import AIMessage

CALLED_AT = "lo9i_called_at"


def stamp(message: AIMessage, at: datetime) -> None:
    """Keeps `at` on a reply that asks for tool calls."""
    if message.tool_calls:
        message.response_metadata[CALLED_AT] = at.isoformat()


def of(message: AIMessage) -> str:
    """When the reply asked for its tool calls, as ISO 8601; "" for one from before it was kept."""
    return str(message.response_metadata.get(CALLED_AT, ""))
