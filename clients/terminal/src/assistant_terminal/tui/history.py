"""Shows an earlier conversation in the chat when it's resumed."""

from textual.containers import VerticalScroll

from assistant.core.agent import ShownMessage
from assistant_terminal.tui.widgets import (
    AssistantMessage,
    CarriedNote,
    FollowUpNote,
    ThinkingNote,
    ToolCall,
    ToolNote,
    UserMessage,
)


async def show_history(chat: VerticalScroll, messages: list[ShownMessage]) -> None:
    await chat.remove_children()
    await chat.mount_all([_widget(m) for m in messages])


def _widget(message: ShownMessage):
    if message.role == "user":
        return UserMessage(message.text, [])
    if message.role == "assistant":
        return AssistantMessage(message.text)
    if message.role == "thinking":
        return ThinkingNote(message.text)
    if message.role == "carried":
        return CarriedNote(message.text)
    if message.role == "notice":
        return FollowUpNote(message.text)
    if message.output:
        return _finished_call(message)
    return ToolNote(message.text)


def _finished_call(message: ShownMessage) -> ToolCall:
    """A handed-off agent's tool call, with its output, as it was shown live."""
    call = ToolCall(message.text, {"detail": message.detail} if message.detail else {})
    call.finish(message.output)
    return call
