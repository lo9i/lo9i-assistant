"""Shows an earlier conversation in the chat when it's resumed: a delegate call with the subagent's steps
inside it, as it was shown live, and any other call with the start of its arguments and output, which loads
in full when it's expanded."""

from collections.abc import Awaitable, Callable
from functools import partial

from textual.containers import VerticalScroll

from assistant.core.agent import ShownCall, ShownMessage
from assistant_terminal.tui.widgets import (
    AssistantMessage,
    CarriedNote,
    FollowUpNote,
    PartialToolCall,
    ThinkingNote,
    ToolCall,
    ToolNote,
    UserMessage,
)

# Loads a tool call in full by its id.
type CallLoader = Callable[[str], Awaitable[ShownCall]]


async def show_history(chat: VerticalScroll, messages: list[ShownMessage], load: CallLoader) -> None:
    await chat.remove_children()
    widgets = [_widget(m, load) for m in messages]
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


def _widget(message: ShownMessage, load: CallLoader):
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
    if message.partial and message.call_id:
        return PartialToolCall(message.text, message.detail, message.output, partial(load, message.call_id))
    if message.output or message.detail:
        return _finished_call(message)
    return ToolNote(message.text)


def _finished_call(message: ShownMessage) -> ToolCall:
    """A tool call with what it was about and its output: a handed-off agent's, a delegate call with its task,
    or one history shows whole, as it was shown live."""
    call = ToolCall(message.text, {"detail": message.detail} if message.detail else {})
    if not message.steps:
        call.finish(message.output)
    return call
