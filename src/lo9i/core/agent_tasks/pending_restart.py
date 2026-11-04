"""What the task tools tell the assistant about a restart or stop of lo9i that's pending (core/ending.py): while it
waits for the runs in progress, messages queued in a conversation aren't sent (daemon/queued.py), a coding task
handed to its agent with the conversation included, so the assistant must know before it hands one over, and can say
why a task it handed over hasn't started."""

from datetime import datetime
from zoneinfo import ZoneInfo

from langgraph.store.base import BaseStore

from lo9i.core import conversations
from lo9i.core.background import short
from lo9i.core.config import settings
from lo9i.core.conversation.queued import Queued
from lo9i.core.ending import AskedEnding

_SHOWN = 80


async def restart_note(asked: AskedEnding, store: BaseStore, user_id: str, here: str = "") -> str:
    """Who asked for it and when, and the runs it waits for; `here` is the conversation the tool runs in."""
    runs = [await _named(store, user_id, thread_id, here) for thread_id in asked.waiting_for]
    waits = f"waiting for {len(runs)} run(s) in progress: {', '.join(runs)}" if runs else "about to go ahead"
    return (
        f"A {asked.ending} of lo9i is pending, asked by {asked.asked_by} at {_local(asked.asked_at)}, {waits}. "
        "Until it happens, messages queued in conversations aren't sent; the user can cancel it or have it go "
        "ahead now from the notice the web app shows."
    )


async def queue_note(waiting: dict[str, list[Queued]], store: BaseStore, user_id: str, here: str = "") -> str:
    """The messages waiting in the queue, by conversation; "" for none."""
    lines = [
        f"- {await _named(store, user_id, thread_id, here)}: {_what(message)}"
        for thread_id, messages in waiting.items()
        for message in messages
    ]
    return "\n".join(["Messages waiting in the queue:", *lines]) if lines else ""


def _what(message: Queued) -> str:
    if message.brief:
        return f"a task for {message.brief}: {short(message.text, _SHOWN)}"
    if message.follow_up:
        return f"a follow-up on work that ended: {short(message.text, _SHOWN)}"
    return f"a message: {short(message.text, _SHOWN)}"


async def _named(store: BaseStore, user_id: str, thread_id: str, here: str) -> str:
    if thread_id == here:
        return "this conversation"
    found = await conversations.load(store, user_id, thread_id)
    return f'"{found.title}" ({thread_id})' if found and found.title else thread_id


def _local(at: str) -> str:
    try:
        return f"{datetime.fromisoformat(at).astimezone(ZoneInfo(settings.timezone)):%Y-%m-%d %H:%M %Z}"
    except ValueError:
        return at
