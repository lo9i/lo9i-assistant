"""Shows an earlier conversation in the chat when it's resumed."""

from textual.containers import VerticalScroll

from assistant.core.agent import ShownMessage
from assistant.gateways.cli.tui.widgets import AssistantMessage, ToolNote, UserMessage


async def show_history(chat: VerticalScroll, messages: list[ShownMessage]) -> None:
    await chat.remove_children()
    await chat.mount_all([_widget(m) for m in messages])


def _widget(message: ShownMessage):
    if message.role == "user":
        return UserMessage(message.text, [])
    if message.role == "assistant":
        return AssistantMessage(message.text)
    return ToolNote(message.text)
