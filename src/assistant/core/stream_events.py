"""Translates LangGraph stream output into gateway events."""

from collections.abc import Iterable
from typing import Any

from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, ToolMessage
from langgraph.types import Interrupt

from assistant.core.events import ApprovalRequired, Error, Event, TextDelta, ToolFinished, ToolStarted


def to_events(mode: str, data: Any) -> list[Event]:
    """Events for one item of `graph.astream(stream_mode=["messages", "updates"])`."""
    if mode == "messages":
        return _chunk_events(*data)
    return _update_events(data)


def approval_events(interrupts: Iterable[Interrupt]) -> list[Event]:
    return [ApprovalRequired(interrupt_id=i.id, request=i.value) for i in interrupts]


def _chunk_events(chunk: BaseMessage, metadata: dict[str, Any]) -> list[Event]:
    if isinstance(chunk, AIMessageChunk) and metadata.get("langgraph_node") == "agent" and chunk.text:
        return [TextDelta(chunk.text)]
    return []


def _update_events(updates: dict[str, Any]) -> list[Event]:
    events: list[Event] = []
    for node, update in updates.items():
        events += approval_events(update) if node == "__interrupt__" else _node_events(update)
    return events


def _node_events(update: dict[str, Any] | None) -> list[Event]:
    events: list[Event] = []
    for message in (update or {}).get("messages", []):
        events += _message_events(message)
    return events


def _message_events(message: BaseMessage) -> list[Event]:
    if isinstance(message, AIMessage):
        return _ai_message_events(message)
    if isinstance(message, ToolMessage):
        return [ToolFinished(name=message.name or "", output=message.text)]
    return []


def _ai_message_events(message: AIMessage) -> list[Event]:
    events: list[Event] = []
    if message.response_metadata.get("stop_reason") == "refusal":
        events.append(Error("The model declined this request."))
    return events + [ToolStarted(name=c["name"], args=c["args"]) for c in message.tool_calls]
