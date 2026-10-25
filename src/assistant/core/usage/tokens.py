"""Splitting a model call's tokens among what was in it: the system prompt, earlier history, the
user's new message, tool results, and the reply (text, or the calls it makes to tools).

Providers report totals only, so the split comes from a local estimate (about 4 characters a token)
scaled to the reported totals: each call's parts add up exactly to what the provider counted. A tool
result counts as the tool's the first time it's sent, in the call right after it ran; later calls
send it again as history (mostly read back from the prompt cache).
"""

import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage

# What an image or a file in a message is taken to weigh. Its text form (base64) would count it
# hundreds of times over.
_MEDIA_TOKENS = 1500
_CHARS_PER_TOKEN = 4
_JOB_PREFIX = "job:"


@dataclass(frozen=True)
class Part:
    kind: str  # system | history | user | tool | reply
    # The tool's name for kind "tool", else "".
    name: str
    input_tokens: int
    output_tokens: int


def input_parts(messages: Sequence[BaseMessage], total: int) -> list[Part]:
    """What follows the last assistant message is new in this call: the user's message, or the
    results of the tools it called. Everything before it is history."""
    last_reply = max((i for i, m in enumerate(messages) if isinstance(m, AIMessage)), default=-1)
    weights: dict[tuple[str, str], int] = {}
    for i, message in enumerate(messages):
        key = _input_kind(message, new=i > last_reply)
        weights[key] = weights.get(key, 0) + _size(message.content)
    shares = _scale(list(weights.values()), total)
    return [Part(kind, name, share, 0) for (kind, name), share in zip(weights, shares, strict=True) if share]


def output_parts(message: AIMessage, total: int) -> list[Part]:
    """The reply's text, and each tool call's arguments as that tool's."""
    weights: dict[tuple[str, str], int] = {("reply", ""): _size(message.text)}
    for call in message.tool_calls:
        key = ("tool", call["name"])
        weights[key] = weights.get(key, 0) + _estimate(json.dumps(call["args"]))
    shares = _scale(list(weights.values()), total)
    return [Part(kind, name, 0, share) for (kind, name), share in zip(weights, shares, strict=True) if share]


def active_skill(messages: Sequence[BaseMessage]) -> str | None:
    """The skill in use: the last one loaded with use_skill since the user's latest message."""
    last_user = max((i for i, m in enumerate(messages) if isinstance(m, HumanMessage)), default=-1)
    skill = None
    for message in messages[last_user + 1 :]:
        if isinstance(message, AIMessage):
            for call in message.tool_calls:
                if call["name"] == "use_skill":
                    skill = str(call["args"].get("name", "")) or skill
    return skill


def job_of(thread_id: str) -> str | None:
    """Scheduled jobs run in their own conversation, `job:<name>:<time>`. Names have no colon; times do."""
    if not thread_id.startswith(_JOB_PREFIX):
        return None
    return thread_id[len(_JOB_PREFIX) :].split(":", 1)[0] or None


def estimate(messages: Sequence[BaseMessage]) -> int:
    """A rough count, for providers that report no usage."""
    return sum(_size(m.content) for m in messages)


def estimate_text(text: str) -> int:
    """A rough count of a text's tokens, at the same rate as the rest."""
    return _estimate(text)


def _input_kind(message: BaseMessage, new: bool) -> tuple[str, str]:
    if isinstance(message, SystemMessage):
        return "system", ""
    if new and isinstance(message, ToolMessage):
        return "tool", message.name or ""
    if new and isinstance(message, HumanMessage):
        return "user", ""
    return "history", ""


def _size(content: Any) -> int:
    if isinstance(content, str):
        return _estimate(content)
    return sum(_block_size(block) for block in content or [])


def _block_size(block: Any) -> int:
    if isinstance(block, str):
        return _estimate(block)
    if not isinstance(block, dict):
        return 0
    if block.get("type") in {"image", "file", "audio", "image_url"}:
        return _MEDIA_TOKENS
    if block.get("type") == "text":
        return _estimate(str(block.get("text", "")))
    return _estimate(json.dumps(block, default=str))


def _estimate(text: str) -> int:
    return -(-len(text) // _CHARS_PER_TOKEN) if text else 0


def _scale(weights: list[int], total: int) -> list[int]:
    """`total` split in proportion to `weights`, in whole tokens that add up to it exactly (the
    largest remainders get the leftover tokens). Without weights, all of it goes to the first."""
    if not weights or total <= 0:
        return [0] * len(weights)
    whole = sum(weights)
    if whole == 0:
        return [total, *([0] * (len(weights) - 1))]
    exact = [w * total / whole for w in weights]
    shares = [int(x) for x in exact]
    leftover = total - sum(shares)
    for i in sorted(range(len(exact)), key=lambda i: exact[i] - shares[i], reverse=True)[:leftover]:
        shares[i] += 1
    return shares
