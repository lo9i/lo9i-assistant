"""Epochs: the conversation never ends, so it is split into epochs (D1, D2).

All messages stay in the checkpoint. State records where the current epoch starts, and
only the current epoch is sent to the model. A new epoch starts on a size limit or an
idle gap: the archived part is digested into an episode, memory is updated, and the
system prompt is rebuilt.
"""

from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage
from langgraph.store.base import BaseStore

from assistant.core.config import settings
from assistant.core.conversation.digest import Digester, DigestInput, EpochDigest
from assistant.core.conversation.prompt import build_system_prompt
from assistant.core.conversation.transcript import render
from assistant.core.identity import load_name
from assistant.core.memory import episodes, facts, profile

_CHARS_PER_TOKEN = 4


async def open_epoch(store: BaseStore, user_id: str, now: datetime, summary: str = "") -> dict[str, Any]:
    """State update that starts an epoch with a freshly built system prompt."""
    name = await load_name(store)
    return {
        "system_prompt": await build_system_prompt(store, user_id, name, summary),
        "assistant_name": name,
        "epoch_summary": summary,
        "epoch_started_at": now.isoformat(),
        "usage_anchor": None,
    }


async def is_renamed(state: Mapping[str, Any], store: BaseStore) -> bool:
    """The user renamed the assistant since this epoch's prompt was built."""
    return state.get("assistant_name", "") != await load_name(store)


async def rename(state: Mapping[str, Any], store: BaseStore, user_id: str, now: datetime) -> dict[str, Any]:
    """A new epoch at the same point, with the prompt rebuilt for the new name. Nothing is
    summarized: the messages stay, only the prompt changes (one cache miss)."""
    return await open_epoch(store, user_id, now, state.get("epoch_summary", ""))


def is_idle(state: Mapping[str, Any], now: datetime) -> bool:
    last = state.get("last_activity")
    return bool(last) and now - datetime.fromisoformat(last) > timedelta(hours=settings.epoch_idle_hours)


def is_too_large(state: Mapping[str, Any]) -> bool:
    return estimate_tokens(state) > settings.epoch_max_tokens


def estimate_tokens(state: Mapping[str, Any]) -> int:
    """Size of the next request (H3): the token count the API reported for the last call,
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
    state: Mapping[str, Any], store: BaseStore, user_id: str, digester: Digester, now: datetime
) -> dict[str, Any]:
    """Archive the older part of the epoch and start a new one. Returns a state update."""
    start = state.get("epoch_start", 0)
    keep = 1 if is_idle(state, now) else settings.epoch_keep_turns
    cut = cut_index(state["messages"], start, keep)
    if cut <= start:
        return {}
    digest = await digester(await _digest_input(state, store, user_id, state["messages"][start:cut]))
    await _save_memory(store, user_id, digest, state, now)
    return {"epoch_start": cut, **await open_epoch(store, user_id, now, digest.conversation_summary)}


async def archive(state: Mapping[str, Any], store: BaseStore, user_id: str, digester: Digester, now: datetime) -> bool:
    """Digest the rest of a conversation that is being left (/new) into an episode and memory.
    Skips conversations with fewer than EPISODE_MIN_TURNS user turns. Returns whether it archived."""
    start = state.get("epoch_start", 0)
    remaining = state.get("messages", [])[start:]
    if sum(isinstance(m, HumanMessage) for m in remaining) < settings.episode_min_turns:
        return False
    digest = await digester(await _digest_input(state, store, user_id, remaining))
    await _save_memory(store, user_id, digest, state, now)
    return True


def cut_index(messages: Sequence[BaseMessage], start: int, keep_turns: int) -> int:
    """Index of the user message that begins the last `keep_turns` turns. Cutting there keeps tool calls paired."""
    turns = [i for i in range(start, len(messages)) if isinstance(messages[i], HumanMessage)]
    if not turns:
        return start
    return turns[-min(max(keep_turns, 1), len(turns))]


async def _digest_input(
    state: Mapping[str, Any], store: BaseStore, user_id: str, archived: Sequence[BaseMessage]
) -> DigestInput:
    return DigestInput(
        previous_summary=state.get("epoch_summary", ""),
        profile=await profile.load(store, user_id),
        facts=await facts.load(store, user_id, settings.memory_max_facts),
        transcript=render(archived),
    )


async def _save_memory(
    store: BaseStore, user_id: str, digest: EpochDigest, state: Mapping[str, Any], now: datetime
) -> None:
    await profile.save(store, user_id, digest.profile)
    for text in digest.new_facts:
        await facts.add(store, user_id, text)
    for fact_id in digest.outdated_fact_ids:
        await facts.remove(store, user_id, fact_id)
    started_at = state.get("epoch_started_at") or now.isoformat()
    ended_at = state.get("last_activity") or now.isoformat()
    await episodes.save(store, user_id, episodes.Episode(started_at, ended_at, digest.episode_summary))
