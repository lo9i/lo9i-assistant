"""Background work that ends after the call that started it returned: a coding agent's task
(core/agent_tasks/ends.py), or work an MCP server reports finished (core/mcp/background.py). Its end is
told to the conversation that started it, in the turn header of the user's next message there
(core/conversation/ended.py), and to the user: it's added to the notifications feed (core/notifications.py)
with a way to open that conversation, every app shows a toast (a `background_ended` event), and a chat
channel it was started from gets a message, kept with that conversation so replying to it goes on there
(core/channels/chat/threads.py). When the work failed, or its end asks for it, the assistant doesn't wait
for the user: a follow-up is queued in that conversation (core/conversation/queued.py), which the daemon
runs with the note and no message from the user.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from langgraph.config import get_config
from langgraph.runtime import get_runtime
from langgraph.store.base import BaseStore

from assistant.core import conversations, inbox, notifications
from assistant.core.bus import EventBus
from assistant.core.channels.chat import threads as chat_threads
from assistant.core.context import UNATTENDED_CHANNEL, Context, thread_of
from assistant.core.conversation import ended, queued, sent
from assistant.core.conversation.queued import Queued
from assistant.core.outbox import DeliveryError, Outbox

logger = logging.getLogger(__name__)

# The feed's title for work started where there's no conversation to open: a scheduled job's run.
_UNLISTED_TITLE = "Background work"


@dataclass(frozen=True)
class Origin:
    """The conversation some work was started in, and the channel the user was on."""

    user_id: str
    thread_id: str
    channel: str


@dataclass(frozen=True)
class Ended:
    # Names the work: the assistant reading its end itself (task_status) drops the note with this key.
    key: str
    ok: bool
    # For the user: the apps' notification and the chat channel's message.
    notice: str
    # For the assistant: a line of the turn header note.
    note: str
    # The assistant follows it up at once, unasked, as it does when the work failed.
    follow_up: bool = False


def current_origin() -> Origin | None:
    """The conversation the running tool call is in; None for a tool called outside a run."""
    runtime = get_runtime(Context)
    if runtime is None:
        return None
    context = runtime.context
    return Origin(context.user_id, thread_of(get_config()), context.channel)


def short(text: str, limit: int) -> str:
    """`text` on one line, cut to `limit` characters, for a notification or a note."""
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit].rstrip() + "…"


class BackgroundEnds:
    def __init__(self, store: BaseStore, outbox: Outbox, bus: EventBus) -> None:
        self._store = store
        self._outbox = outbox
        self._bus = bus

    async def deliver(self, origin: Origin, work: Ended) -> None:
        """A scheduled job's conversation is never written in again, so it gets no note, and the feed has no
        conversation to open for it."""
        attended = origin.channel != UNATTENDED_CHANNEL
        if attended:
            await ended.record(self._store, origin.user_id, origin.thread_id, work.key, work.note)
        await self._notify(origin, work, attended)
        self._bus.publish(
            "background_ended", thread_id=origin.thread_id, channel=origin.channel, ok=work.ok, text=work.notice
        )
        if origin.channel in self._outbox.channels:
            await self._message(origin, work.notice, attended)
        if attended and (work.follow_up or not work.ok):
            await queued.add(self._store, origin.user_id, origin.thread_id, Queued(origin.channel, work.notice, True))

    async def _notify(self, origin: Origin, work: Ended, attended: bool) -> None:
        """Into the feed, named after the conversation it was started in."""
        started_in = await conversations.load(self._store, origin.user_id, origin.thread_id) if attended else None
        title = started_in.title if started_in else _UNLISTED_TITLE
        thread_id = started_in.thread_id if started_in else ""
        await notifications.add(self._store, origin.user_id, "background", title, work.notice, work.ok, thread_id)

    async def _message(self, origin: Origin, text: str, attended: bool) -> None:
        """Like send_message: replying to it goes on in the conversation the work was started in, and a
        channel now on another conversation hears of it there too, in the turn header of the user's next
        message on it."""
        try:
            sent_ids = await self._outbox.send(origin.channel, text)
        except DeliveryError as e:
            logger.warning("Couldn't tell %s that background work ended: %s", origin.channel, e)
            return
        if attended:
            await chat_threads.record_own(self._store, origin.user_id, origin.channel, sent_ids, origin.thread_id)
        if await inbox.channel_thread(self._store, origin.user_id, origin.channel) != origin.thread_id:
            await sent.record(self._store, origin.user_id, origin.channel, text, datetime.now(UTC))
