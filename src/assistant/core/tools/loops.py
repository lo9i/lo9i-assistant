"""Tools for the user's open loops (core/proactive/loops.py) and the kinds of suggestion they muted: what the morning
briefing, the reviews and reminders bring up (core/proactive/)."""

from typing import Literal

from langchain_core.tools import tool
from langgraph.prebuilt import ToolRuntime
from pydantic import ValidationError

from assistant.core.context import Context, require_store, thread_of
from assistant.core.proactive import loops, records
from assistant.core.proactive.model import LoopDraft, LoopStatus, OpenLoop
from assistant.core.tools.registry import register

ListedStatus = Literal["open", "done", "dismissed", "all"]
_GROUP = "open-loops"
_LISTED = 50


@register("memory", subagents=True, group=_GROUP)
@tool
async def list_open_loops(runtime: ToolRuntime[Context], status: ListedStatus = "open") -> str:
    """The user's open loops (what's still to do, waiting on someone, or promised to them), with their ids, and
    the kinds of suggestion they muted. `status`: open, done, dismissed or all."""
    store, user_id = require_store(runtime.store), runtime.context.user_id
    found = [o for o in await loops.all_loops(store, user_id) if status in ("all", o.status)][:_LISTED]
    muted = (await records.load_settings(store, user_id)).muted
    listed = "\n".join(_line(o) for o in found) or ("No loops." if status == "all" else f"No {status} loops.")
    return f"{listed}\n\nMuted kinds: {', '.join(muted) or 'none'}."


@register("memory", group=_GROUP)
@tool
async def add_open_loop(
    text: str, runtime: ToolRuntime[Context], kind: str = "", due: str = "", remind_at: str = ""
) -> str:
    """Keep something the user still has to do or is waiting for as an open loop, which the morning briefing lists
    until it's closed. `due`: its day, YYYY-MM-DD. `remind_at`: only when the user asks to be reminded at a time
    (local YYYY-MM-DDTHH:MM); the reminder goes to their chat channels."""
    try:
        draft = LoopDraft(text=text, kind=kind, due=due, remind_at=remind_at)
    except ValidationError as e:
        return f"Not added: {e.errors()[0]['msg']}."
    store = require_store(runtime.store)
    added = await loops.add(store, runtime.context.user_id, draft, "assistant", _thread(runtime))
    return f"Added {added.id}." if added else "Not added: a loop like it was added before (see list_open_loops all)."


@register("memory", group=_GROUP)
@tool
async def close_open_loop(
    loop_id: str, runtime: ToolRuntime[Context], status: LoopStatus = "done", stop_suggesting: bool = False
) -> str:
    """Close an open loop the user did (`done`) or doesn't want (`dismissed`), or open it again (`open`). With
    `stop_suggesting`, its kind is muted too: nothing of that kind is suggested again."""
    store, user_id = require_store(runtime.store), runtime.context.user_id
    closed = await loops.close(store, user_id, loop_id, status)
    if closed is None:
        return f"No loop {loop_id}."
    if stop_suggesting and closed.kind:
        await records.mute(store, user_id, closed.kind)
        return f"{loop_id} is {status}; {closed.kind!r} won't be suggested again."
    return f"{loop_id} is {status}."


@register("memory", group=_GROUP)
@tool
async def mute_suggestions(kind: str, runtime: ToolRuntime[Context], muted: bool = True) -> str:
    """When the user doesn't want a kind of suggestion or reminder from the briefing and reviews ("less of this",
    "stop reminding me about mail"), mute that kind, in a few words (automation suggestion, unanswered mail, bill
    due, invoices to issue, missing calendar entry, recurring task). `muted` false suggests it again."""
    chosen = await records.mute(require_store(runtime.store), runtime.context.user_id, kind, muted)
    return f"Muted kinds: {', '.join(chosen.muted) or 'none'}."


def _line(loop: OpenLoop) -> str:
    details = [loop.status, f"since {loop.created_at[:10]}"]
    details += [f"due {loop.due}"] if loop.due else []
    details += [loop.kind] if loop.kind else []
    return f"- [{loop.id}] {loop.text} ({'; '.join(details)})"


def _thread(runtime: ToolRuntime[Context]) -> str:
    """The conversation it was added in; a scheduled run's isn't one to open."""
    return "" if runtime.context.unattended else thread_of(runtime.config)
