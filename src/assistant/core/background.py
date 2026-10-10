"""Background work that ends after the call that started it returned: a coding agent's task
(core/agent_tasks/ends.py), or work an MCP server reports finished (core/mcp/background.py). Its end is
told to the conversation that started it, in the turn header of the user's next message there
(core/conversation/ended.py), and to the user: every app shows a notification (a `background_ended`
event), and a chat channel it was started from gets a message.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from langgraph.config import get_config
from langgraph.runtime import get_runtime
from langgraph.store.base import BaseStore

from assistant.core import home
from assistant.core.bus import EventBus
from assistant.core.context import UNATTENDED_CHANNEL, Context, thread_of
from assistant.core.conversation import ended, sent
from assistant.core.outbox import DeliveryError, Outbox

logger = logging.getLogger(__name__)


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
        """A scheduled job's conversation is never written in again, so it gets no note."""
        if origin.channel != UNATTENDED_CHANNEL:
            await ended.record(self._store, origin.user_id, origin.thread_id, work.key, work.note)
        self._bus.publish(
            "background_ended", thread_id=origin.thread_id, channel=origin.channel, ok=work.ok, text=work.notice
        )
        if origin.channel in self._outbox.channels:
            await self._message(origin, work.notice)

    async def _message(self, origin: Origin, text: str) -> None:
        """Like send_message: a channel now on another conversation hears of it there too, in the turn
        header of the user's next message on it."""
        try:
            await self._outbox.send(origin.channel, text)
        except DeliveryError as e:
            logger.warning("Couldn't tell %s that background work ended: %s", origin.channel, e)
            return
        if await home.channel_thread(self._store, origin.user_id, origin.channel) != origin.thread_id:
            await sent.record(self._store, origin.user_id, origin.channel, text, datetime.now(UTC))
