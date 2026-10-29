"""The terminal app's open conversations, as the web app's sidebar lists them under Chat (its lib/chat/openList.ts):
the ones opened here, in the order they were, then every other one with something working in it (a reply, a coding
task), whoever started it. Never the inbox."""

from dataclasses import dataclass

from rich.markup import escape

from assistant.core.agent import Conversation
from assistant_terminal.i18n import t


@dataclass(frozen=True)
class OpenItem:
    thread_id: str
    title: str
    # Opened here, so it can be closed; one working elsewhere isn't.
    opened: bool
    # The one shown.
    current: bool
    running: bool
    # A question or approval waits for the user.
    waiting: bool


def open_list(
    opened: list[str],
    current: str,
    inbox: str,
    conversations: list[Conversation],
    working: set[str],
    waiting: set[str],
) -> list[OpenItem]:
    """`working`: the conversations with a reply or a task running anywhere; `waiting`: those whose run waits for an
    answer."""
    titles = {c.thread_id: c.title for c in conversations}
    inboxes = {inbox, *(c.thread_id for c in conversations if c.inbox)}

    def item(thread_id: str, opened_here: bool) -> OpenItem:
        title = titles.get(thread_id) or t("new conversation")
        busy, asks = thread_id in working, thread_id in waiting
        return OpenItem(thread_id, title, opened_here, thread_id == current, busy, asks)

    shown = [item(i, True) for i in opened if i not in inboxes]
    listed = {i.thread_id for i in shown}
    elsewhere = [item(c.thread_id, False) for c in conversations if c.thread_id in working - inboxes - listed]
    return [*shown, *elsewhere]


def line(item: OpenItem) -> str:
    """The item as a line of the list: what it's doing, its title, which one is shown."""
    marker = "?" if item.waiting else "●" if item.running else " "
    states = [
        *([t("waiting for you")] if item.waiting else []),
        *([t("working")] if item.running and not item.waiting else []),
        *([t("shown")] if item.current else []),
        *([t("not opened here")] if not item.opened else []),
    ]
    return f"{marker} {escape(item.title)}" + (f"  [dim]({', '.join(states)})[/dim]" if states else "")
