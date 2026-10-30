"""Epochs: the conversation never ends, so it is split into epochs (D1, D2).

All messages stay in the checkpoint. State records where the current epoch starts, and
only the current epoch is sent to the model. A new epoch starts on a size limit or an
idle gap: the archived part is summarized into the rebuilt system prompt, and left for the
memory writer (memory_writer.py) to digest into an episode and memory after the reply.
"""

from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage
from langgraph.store.base import BaseStore

from assistant.core.config import settings
from assistant.core.conversation import pending, pinned, prompt_edits, summaries
from assistant.core.conversation.pending import PendingPart
from assistant.core.conversation.prompt import build_system_prompt
from assistant.core.conversation.summary import Summarizer
from assistant.core.conversation.transcript import render
from assistant.core.identity import load_name

_CHARS_PER_TOKEN = 4


async def open_epoch(
    store: BaseStore,
    user_id: str,
    thread_id: str,
    now: datetime,
    plugin_tools: Mapping[str, Sequence[str]],
    summary: str = "",
) -> dict[str, Any]:
    """State update that starts an epoch with a freshly built system prompt. `plugin_tools`: the plugins
    whose tools it can load (core/plugin_loading.py), which the graph keeps with the epoch."""
    name = await load_name(store)
    pinned_skills = await pinned.load(store, user_id, thread_id)
    texts = await prompt_edits.current()
    return {
        "system_prompt": await build_system_prompt(store, user_id, name, summary, pinned_skills, texts, plugin_tools),
        "assistant_name": name,
        "prompt_texts": prompt_edits.digest(texts),
        "pinned_skills": pinned_skills,
        "epoch_summary": summary,
        "epoch_started_at": now.isoformat(),
        "usage_anchor": None,
    }


async def is_renamed(state: Mapping[str, Any], store: BaseStore) -> bool:
    """The user renamed the assistant since this epoch's prompt was built."""
    return state.get("assistant_name", "") != await load_name(store)


async def is_repinned(state: Mapping[str, Any], store: BaseStore, user_id: str, thread_id: str) -> bool:
    """The user pinned or unpinned a skill since this epoch's prompt was built."""
    return state.get("pinned_skills", []) != await pinned.load(store, user_id, thread_id)


async def is_reworded(state: Mapping[str, Any]) -> bool:
    """The user edited a prompt text (prompt_edits.py) since this epoch's prompt was built, or an update
    changed a built-in one."""
    return state.get("prompt_texts", "") != prompt_edits.digest(await prompt_edits.current())


async def reopen(
    state: Mapping[str, Any],
    store: BaseStore,
    user_id: str,
    thread_id: str,
    now: datetime,
    plugin_tools: Mapping[str, Sequence[str]],
) -> dict[str, Any]:
    """A new epoch at the same point, after a rename, a pinned skill, an edited prompt text or a change in
    the plugins' tools.
    Nothing is summarized: the messages stay, only the prompt and tools change (one cache miss)."""
    return await open_epoch(store, user_id, thread_id, now, plugin_tools, state.get("epoch_summary", ""))


def is_idle(state: Mapping[str, Any], now: datetime) -> bool:
    last = state.get("last_activity")
    return bool(last) and now - datetime.fromisoformat(last) > timedelta(hours=settings.epoch_idle_hours)


def is_too_large(state: Mapping[str, Any]) -> bool:
    return estimate_tokens(state) > settings.epoch_max_tokens


def estimate_tokens(state: Mapping[str, Any]) -> int:
    """Size of the next request: the token count the API reported for the last call,
    plus an estimate for messages added since. Falls back to a character estimate when the
    epoch has no reported count yet."""
    anchor = state.get("usage_anchor")
    if anchor:
        return anchor["tokens"] + _estimate(state["messages"][anchor["messages"] :])
    epoch = state["messages"][state.get("epoch_start", 0) :]
    return len(state.get("system_prompt", "")) // _CHARS_PER_TOKEN + _estimate(epoch)


def usage_anchor(response: BaseMessage, message_count: int) -> dict[str, int] | None:
    """Reported size of a model call: tokens in and out, and how many messages it covered."""
    usage = getattr(response, "usage_metadata", None)
    if not usage:
        return None
    return {"tokens": usage["input_tokens"] + usage["output_tokens"], "messages": message_count}


def _estimate(messages: Sequence[BaseMessage]) -> int:
    return len(render(messages)) // _CHARS_PER_TOKEN


async def compact(
    state: Mapping[str, Any],
    store: BaseStore,
    user_id: str,
    thread_id: str,
    summarizer: Summarizer,
    now: datetime,
    plugin_tools: Mapping[str, Sequence[str]],
    keep_turns: int | None = None,
) -> dict[str, Any]:
    """Archive the older part of the epoch and start a new one with its last `keep_turns` user turns (by default
    EPOCH_KEEP_TURNS, or the last one after an idle gap). Returns a state update."""
    start = state.get("epoch_start", 0)
    keep = keep_turns or (1 if is_idle(state, now) else settings.epoch_keep_turns)
    cut = cut_index(state["messages"], start, keep)
    if cut <= start:
        return {}
    summary = await summarizer(state.get("epoch_summary", ""), render(state["messages"][start:cut]))
    await pending.add(store, user_id, _part(state, thread_id, start, cut, now))
    await summaries.save(store, user_id, thread_id, summary)
    return {"epoch_start": cut, **await open_epoch(store, user_id, thread_id, now, plugin_tools, summary)}


async def archive(
    state: Mapping[str, Any], store: BaseStore, user_id: str, thread_id: str, now: datetime, after: int = 0
) -> bool:
    """Leave the rest of a conversation that is being left (/clear) to be digested into an episode
    and memory, from message `after` on when that's past the epoch start (it was archived before,
    then resumed). Skips fewer than EPISODE_MIN_TURNS user turns. Returns whether it archived."""
    messages = state.get("messages", [])
    start = max(state.get("epoch_start", 0), after)
    if sum(isinstance(m, HumanMessage) for m in messages[start:]) < settings.episode_min_turns:
        return False
    await pending.add(store, user_id, _part(state, thread_id, start, len(messages), now))
    return True


def cut_index(messages: Sequence[BaseMessage], start: int, keep_turns: int) -> int:
    """Index of the user message that begins the last `keep_turns` turns. Cutting there keeps tool calls paired."""
    turns = [i for i in range(start, len(messages)) if isinstance(messages[i], HumanMessage)]
    if not turns:
        return start
    return turns[-min(max(keep_turns, 1), len(turns))]


def _part(state: Mapping[str, Any], thread_id: str, start: int, end: int, now: datetime) -> PendingPart:
    return PendingPart(
        thread_id=thread_id,
        start=start,
        end=end,
        previous_summary=state.get("epoch_summary", ""),
        started_at=state.get("epoch_started_at") or now.isoformat(),
        ended_at=state.get("last_activity") or now.isoformat(),
    )
