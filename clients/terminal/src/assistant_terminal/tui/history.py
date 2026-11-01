"""Shows an earlier conversation in the chat when it's resumed: a delegate call with the subagent's steps
inside it, as it was shown live, and any other call with the start of its arguments and output, which loads
in full when it's expanded; so does a step inside a call that shows only its start. What the user sent while an update
installed, which runs once lo9i is back on it, shows with the note it showed with when it was sent."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from functools import partial

from textual.containers import VerticalScroll

from assistant.core.agent import ShownCall, ShownMessage
from assistant.core.conversation import choices
from assistant_terminal.tui.widgets import (
    RESENT,
    UNTAKEN,
    AssistantMessage,
    BriefNote,
    CarriedNote,
    ChoicesNote,
    ErrorMessage,
    FollowUpNote,
    HeldNote,
    PartialToolCall,
    ThinkingNote,
    ToolCall,
    ToolNote,
    UserMessage,
)


@dataclass(frozen=True)
class Loaders:
    """Load a tool call in full by its id, and a step inside one by the call's id and its place from 0."""

    call: Callable[[str], Awaitable[ShownCall]]
    step: Callable[[str, int], Awaitable[ShownCall]]


async def show_history(chat: VerticalScroll, messages: list[ShownMessage], load: Loaders) -> None:
    await chat.remove_children()
    widgets = [_widget(m, load) for m in messages]
    await chat.mount_all([shown for w, m in zip(widgets, messages, strict=True) for shown in (w, *_held(m))])
    if messages and messages[-1].role == "assistant" and (offered := choices.offered(messages[-1].text)):
        await chat.mount(ChoicesNote(offered))
    # A delegate call takes its steps once it's mounted, then ends, as it did live.
    for widget, message in zip(widgets, messages, strict=True):
        if message.steps and isinstance(widget, ToolCall):
            await _add_steps(widget, message, load)


async def _add_steps(call: ToolCall, message: ShownMessage, load: Loaders) -> None:
    for place, step in enumerate(message.steps):
        if step.partial and message.call_id:
            await call.add_step(
                PartialToolCall(step.name, step.args, step.output, partial(load.step, message.call_id, place))
            )
            continue
        shown = ToolCall(step.name, step.args)
        await call.add_step(shown)
        shown.finish(step.output)
    call.finish(message.output)


def _held(message: ShownMessage) -> list[HeldNote]:
    """Its run, once it starts, doesn't show the message again (`HeldNote.held_id`)."""
    return [HeldNote(message.held)] if message.held else []


def _widget(message: ShownMessage, load: Loaders):
    if message.role == "user":
        return UserMessage(message.text, [], UNTAKEN if message.untaken else RESENT if message.resent else "")
    if message.role == "assistant":
        return AssistantMessage(choices.without_markers(message.text).strip())
    if message.role == "thinking":
        return ThinkingNote(message.text)
    if message.role == "carried":
        return CarriedNote(message.text)
    if message.role == "brief":
        return BriefNote(message.text, message.agent)
    if message.role == "notice":
        return FollowUpNote(message.text)
    if message.role == "error":
        return ErrorMessage(message.text)
    if message.partial and message.call_id:
        about = {"detail": message.detail} if message.detail else {}
        return PartialToolCall(message.text, about, message.output, partial(load.call, message.call_id))
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
