"""Shows an earlier conversation in the chat when it's resumed: a delegate call with the subagent's steps
inside it, as it was shown live."""

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
    widgets = [_widget(m) for m in messages]
    await chat.mount_all(widgets)
    # A delegate call takes its steps once it's mounted, then ends, as it did live.
    for widget, message in zip(widgets, messages, strict=True):
        if message.steps and isinstance(widget, ToolCall):
            await _add_steps(widget, message)


async def _add_steps(call: ToolCall, message: ShownMessage) -> None:
    for step in message.steps:
        shown = ToolCall(step.name, step.args)
        await call.add_step(shown)
        shown.finish(step.output)
    call.finish(message.output)


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
    """A handed-off agent's tool call, or a delegate call with its task, with its output, as it was shown
    live."""
    call = ToolCall(message.text, {"detail": message.detail} if message.detail else {})
    if not message.steps:
        call.finish(message.output)
    return call
