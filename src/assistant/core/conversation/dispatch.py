"""Where a message written in the inbox (core/inbox.py) goes: on in the conversation it continues, into a
new one, or, for a quick question one answer settles, answered right in the inbox. The worker model picks
among the conversations the message most likely continues (their tags matched as in related.py, then the
most recent), with how sure it is; the graph moves it without asking (core/conversation/dispatch_nodes.py).
Archived conversations are never picked."""

import re
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage
from langgraph.store.base import BaseStore

from assistant.core import conversations
from assistant.core.conversation import prompts, related
from assistant.core.conversation.search import MessageIndex
from assistant.core.llm import build_llm, metered
from assistant.core.llm.choice import ModelChoice
from assistant.core.usage.log import UsageLog
from assistant.core.usage.meter import TokenMeter

_PROMPT = prompts.load("dispatch")
_EXCHANGE = prompts.load("dispatch_exchange")
# The conversations the model chooses among: those the message's words match first, then the most recent.
_CANDIDATES = 15
_OPENING_CHARS = 200
_LINE = re.compile(r"^[^\w\n]*(pick|confidence|else)[^\w\n]*?:[^\w\n]*([\w.]+)", re.IGNORECASE | re.MULTILINE)

# Places that aren't conversations: a new quick question the inbox answers, and one that follows up the
# inbox's last quick question. A conversation's place is its id; a new conversation's is "".
QUICK, FOLLOW_UP = "quick", "follow_up"


@dataclass(frozen=True)
class Candidate:
    thread_id: str
    title: str
    tags: list[str]
    # The start of its first message.
    opening: str
    # When it was last written in, as "3 hours ago".
    active: str = ""


@dataclass(frozen=True)
class Pick:
    """Where the message goes (a conversation's id, "" for a new one, QUICK or FOLLOW_UP), how sure the
    model is, and `other`, the next most likely place."""

    place: str
    confidence: float
    other: str


# The message, the conversations it may continue, and the inbox's quick exchange in progress ("" for none).
Classifier = Callable[[str, Sequence[Candidate], str], Awaitable[Pick]]


def build_classifier(choice: ModelChoice, usage: UsageLog) -> Classifier:
    """On the worker model, built at the first message to route. Its calls are recorded in `usage` as
    dispatch."""
    built: list[BaseChatModel] = []

    async def _classify(message: str, candidates: Sequence[Candidate], exchange: str) -> Pick:
        if not built:
            built.append(metered(build_llm(choice, choice.worker_model), TokenMeter(usage, "dispatch")))
        listed = "\n".join(_line(i, c) for i, c in enumerate(candidates, 1)) or "(none yet)"
        going_on = _EXCHANGE.format(exchange=exchange) if exchange else ""
        prompt = _PROMPT.format(conversations=listed, message=message, exchange=going_on)
        reply = await built[0].ainvoke([HumanMessage(prompt)])
        return parse(reply.text, candidates, bool(exchange))

    return _classify


async def candidates(
    store: BaseStore, search: MessageIndex, user_id: str, inbox_id: str, message: str
) -> list[Candidate]:
    """The conversations `message` may continue: those its words match, then the most recent."""
    listed = [c for c in await conversations.recent(store, user_id) if c.thread_id != inbox_id and not c.archived]
    matched = related.matches(message, {c.thread_id: c.tags for c in listed})
    ordered = [*matched, *(c.thread_id for c in listed if c.thread_id not in matched)][:_CANDIDATES]
    by_id = {c.thread_id: c for c in listed}
    openings = await search.first_user_messages(user_id, ordered)
    now = datetime.now(UTC)
    return [_candidate(by_id[t], openings.get(t, ""), now) for t in ordered]


def parse(reply: str, candidates: Sequence[Candidate], exchange: bool = False) -> Pick:
    """A reply that can't be read starts a new conversation nobody is sure of. A follow-up when the inbox
    has no exchange going on is a quick question."""
    found = {name.lower(): value for name, value in _LINE.findall(reply)}

    def place(name: str) -> str:
        value = found.get(name, "0").lower()
        if value in ("q", "f"):
            return FOLLOW_UP if value == "f" and exchange else QUICK
        try:
            number = int(float(value))
        except ValueError:
            return ""
        return candidates[number - 1].thread_id if 1 <= number <= len(candidates) else ""

    try:
        confidence = min(max(float(found.get("confidence", "0")), 0.0), 1.0)
    except ValueError:
        return Pick("", 0.0, "")
    return Pick(place("pick"), confidence, place("else"))


def _candidate(conversation: conversations.Conversation, opening: str, now: datetime) -> Candidate:
    line = " ".join(opening.split())
    line = line if len(line) <= _OPENING_CHARS else line[: _OPENING_CHARS - 1] + "…"
    active = ago(_aware(datetime.fromisoformat(conversation.updated_at)), now) if conversation.updated_at else ""
    return Candidate(conversation.thread_id, conversation.title, conversation.tags, line, active)


def _aware(at: datetime) -> datetime:
    """Records keep UTC; one written without a zone is UTC too."""
    return at if at.tzinfo else at.replace(tzinfo=UTC)


def ago(then: datetime, now: datetime) -> str:
    """ "just now", "5 minutes ago", "3 hours ago", "2 days ago"."""
    minutes = int((now - then).total_seconds() // 60)
    for size, unit in ((24 * 60, "day"), (60, "hour"), (1, "minute")):
        if minutes >= size:
            count = minutes // size
            return f"{count} {unit}{'s' if count > 1 else ''} ago"
    return "just now"


def _line(number: int, candidate: Candidate) -> str:
    tags = f" ({', '.join(candidate.tags)})" if candidate.tags else ""
    active = f" Last written {candidate.active}." if candidate.active else ""
    return f'{number}. "{candidate.title}"{tags}.{active} It began: {candidate.opening or "(unknown)"}'
