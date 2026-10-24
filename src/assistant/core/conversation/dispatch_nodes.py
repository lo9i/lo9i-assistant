"""The graph's first steps. In the inbox (core/inbox.py), a message is routed without asking: the worker
model picks where it goes (dispatch.py). A quick question is answered right there; anything else isn't
answered in the inbox: the message is kept for the client to send on (dispatched.py, a Dispatched event) to
the conversation it continues, or a new one when the model isn't sure enough. The inbox keeps the message
and a line saying where it went, so it's the record of what went where. Anywhere else, and in unattended
runs, the run goes on to the epoch and the agent.

A quick exchange in the inbox lasts INBOX_TURNS of the user's messages: the next one about it moves to a
new conversation, which gets what was said so far in a note, so it picks the exchange up.

A message already sent on can be moved: a run in the inbox whose input is `{"dispatching": {"move": id}}`
picks again among the other conversations, asks the user (moving is their correction, so they choose), and
sends it on again by the same id. Skipping that question leaves it where it is."""

import logging
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.config import get_stream_writer
from langgraph.graph import END
from langgraph.runtime import Runtime
from langgraph.store.base import BaseStore
from langgraph.types import Command, interrupt

from assistant.core import inbox
from assistant.core.context import Context, require_search, require_store, thread_of
from assistant.core.conversation import carried, dispatch_setting, dispatched, ended, follow_up
from assistant.core.conversation.dispatch import FOLLOW_UP, QUICK, Candidate, Classifier, Pick, candidates
from assistant.core.conversation.dispatched import DISPATCH_ID
from assistant.core.conversation.turn_header import is_date_header, said
from assistant.core.events import QUESTION, Dispatched

DISPATCH, ASK, SEND = "dispatch", "dispatch_ask", "dispatch_send"
INBOX_TURNS = 2
# What a Dispatched event calls a new conversation, which has no title yet.
NEW_TITLE = "New conversation"
_NEW = "A new conversation"
# Telegram and Slack buttons show about this much (core/tools/questions.py).
_OPTION_CHARS = 60
_QUOTED_CHARS = 120
# How much of each message of a quick exchange the classifier reads, and a new conversation is given.
_EXCHANGE_CHARS = 300
_CARRIED_CHARS = 2000

Node = Callable[..., Awaitable[Any]]

logger = logging.getLogger(__name__)


def dispatch_nodes(classify: Classifier, then: str) -> dict[str, Node]:
    """The nodes by name; `then` is where a run that isn't routed goes on."""
    return {DISPATCH: _dispatch_node(classify, then), ASK: _ask, SEND: _send}


def _dispatch_node(classify: Classifier, then: str) -> Node:
    async def _dispatch(state: dict[str, Any], runtime: Runtime[Context], config: RunnableConfig) -> Command:
        context, store = runtime.context, require_store(runtime.store)
        if move := (state.get("dispatching") or {}).get("move"):
            return await _moving(classify, runtime, move)
        message = _last_user_message(state["messages"])
        # A follow-up on background work (core/agent/follow_ups.py) has nothing of the user's to route.
        if message is None or context.unattended or ended.follow_up_notice(message):
            return Command(goto=then)
        inbox_id = await inbox.current(store, context.user_id)
        if inbox_id is None or thread_of(config) != inbox_id:
            return Command(goto=then)
        found = await candidates(
            store, require_search(context), context.user_id, inbox_id, said(message), context.similar
        )
        exchange = state.get("inbox_exchange")
        pick = await _picked(classify, store, context.user_id, state["messages"], exchange, found)
        return _routed(state["messages"], exchange, pick, found, then)

    return _dispatch


async def _picked(
    classify: Classifier,
    store: BaseStore,
    user_id: str,
    messages: list[BaseMessage],
    exchange: dict[str, int] | None,
    found: Sequence[Candidate],
) -> Pick:
    """Where the message goes: where the one before it went when it obviously follows it up (follow_up.py),
    else the model's pick, a new conversation when it isn't sure enough. Each pick is logged with where the
    message before went, which measures how often the model's call could be skipped."""
    if exchange is None and (place := await follow_up.obvious(store, user_id, messages, found)):
        logger.info("Routed a message to %s, the conversation it follows up, without the model.", place)
        return Pick(place, 1.0, "")
    pick = await classify(said(messages[-1]), found, _exchange_text(messages, exchange))
    sure = pick if pick.confidence >= (await dispatch_setting.load(store)).confidence else Pick("", 0.0, "")
    last = await follow_up.last_place(store, user_id, messages)
    logger.info("The model routed a message to %s; the one before went to %s.", sure.place or "new", last or "-")
    return sure


def _routed(
    messages: list[BaseMessage], exchange: dict[str, int] | None, pick: Pick, found: Sequence[Candidate], then: str
) -> Command:
    """Answered in the inbox (`then`), or sent on: a quick exchange that went on long enough is carried."""
    titles = {c.thread_id: c.title for c in found}
    if pick.place == QUICK:
        return Command(goto=then, update={"inbox_exchange": {"start": len(messages) - 1, "turns": 1}})
    if pick.place == FOLLOW_UP and exchange is not None and exchange["turns"] < INBOX_TURNS:
        return Command(goto=then, update={"inbox_exchange": exchange | {"turns": exchange["turns"] + 1}})
    dispatching: dict[str, Any] = {"thread_id": _conversation(pick.place), "other": "", "titles": titles}
    if pick.place == FOLLOW_UP and exchange is not None:
        dispatching["carried"] = carried.lines(messages[exchange["start"] : -1], _CARRIED_CHARS)
    return Command(goto=SEND, update={"dispatching": dispatching, "inbox_exchange": None})


async def _moving(classify: Classifier, runtime: Runtime[Context], dispatch_id: str) -> Command:
    """Picks again for a message already sent on, leaving out the conversation it's in."""
    context, store = runtime.context, require_store(runtime.store)
    kept = await dispatched.load(store, context.user_id, dispatch_id)
    inbox_id = await inbox.current(store, context.user_id)
    if kept is None or inbox_id is None:
        return Command(goto=END, update={"dispatching": None})
    found = await candidates(store, require_search(context), context.user_id, inbox_id, kept.said, context.similar)
    others = [c for c in found if c.thread_id != kept.sent_to]
    pick = await classify(kept.said, others, "")
    titles = {c.thread_id: c.title for c in others}
    dispatching = {
        "thread_id": _conversation(pick.place),
        "other": _conversation(pick.other),
        "titles": titles,
        "id": kept.id,
        "said": kept.said,
        "carried": kept.carried,
    }
    return Command(goto=ASK, update={"dispatching": dispatching})


async def _ask(state: dict[str, Any]) -> Command:
    dispatching = state["dispatching"]
    likely = next(iter(dispatching["titles"]), "")
    places = list(dict.fromkeys([dispatching["thread_id"], dispatching["other"], likely, ""]))[:3]
    labels = {_label(p, dispatching["titles"]): p for p in places}
    quoted = _shortened(_said(state, dispatching), _QUOTED_CHARS)
    asked = f"Where should this go instead? “{quoted}”"
    answer = interrupt({"kind": QUESTION, "question": asked, "options": list(labels), "multiple": False})
    choices = answer.get("choices") if isinstance(answer, dict) else None
    if not choices:
        return Command(goto=END, update={"dispatching": None})
    chosen = labels.get(choices[0], "")
    return Command(goto=SEND, update={"dispatching": dispatching | {"thread_id": chosen}})


async def _send(state: dict[str, Any], runtime: Runtime[Context]) -> Command:
    dispatching = state["dispatching"]
    text = _said(state, dispatching)
    exchange = dispatching.get("carried", [])
    dispatch_id = dispatching.get("id") or await _keep(state, runtime, text, exchange)
    thread_id = dispatching["thread_id"]
    title = dispatching["titles"].get(thread_id, "")
    line = _line(thread_id, title, text if "id" in dispatching else "", bool(exchange))
    shown = carried.shown(exchange)
    get_stream_writer()(Dispatched(dispatch_id, thread_id, title or NEW_TITLE, text, line, shown))
    recorded = AIMessage(line, response_metadata={DISPATCH_ID: dispatch_id})
    return Command(goto=END, update={"messages": [recorded], "dispatching": None})


async def _keep(state: dict[str, Any], runtime: Runtime[Context], text: str, exchange: list[carried.Line]) -> str:
    """Keeps the message the inbox got, without its date header, and returns its id. Its notes go with it
    (messages sent on the channel from elsewhere, work that ended in the inbox), and a quick exchange it
    follows up comes with it, as one more note and for the apps to show (carried.py)."""
    message = _last_user_message(state["messages"]) or HumanMessage("")
    blocks = message.content if isinstance(message.content, list) else [{"type": "text", "text": message.content}]
    content = [b for b in blocks if not is_date_header(b)]
    if exchange:
        content = [carried.note(exchange), *content]
    store, user_id = require_store(runtime.store), runtime.context.user_id
    return await dispatched.keep(store, user_id, content, text, carried=exchange)


def _line(thread_id: str, title: str, moved: str, carried: bool) -> str:
    """What the inbox records for a message it sent on; `moved` is what a message moved later said."""
    if moved:
        quoted = _shortened(moved, _OPTION_CHARS)
        return f"→ Moved “{quoted}” to “{title}”." if thread_id else f"→ Moved “{quoted}” to a new conversation."
    if carried:
        return "→ Took this to a new conversation, with the quick exchange before it."
    return f"→ Continued in “{title}”." if thread_id else "→ Started a new conversation."


def _exchange_text(messages: list[BaseMessage], exchange: dict[str, int] | None) -> str:
    """The inbox's quick exchange in progress, for the classifier; "" for none."""
    return carried.transcript(carried.lines(messages[exchange["start"] : -1], _EXCHANGE_CHARS)) if exchange else ""


def _conversation(place: str) -> str:
    """A conversation's id, or "" for a new one: the inbox's own places aren't conversations."""
    return "" if place in (QUICK, FOLLOW_UP) else place


def _said(state: dict[str, Any], dispatching: dict[str, Any]) -> str:
    """What the message being sent on said: a moved one's is kept with it."""
    if "said" in dispatching:
        return dispatching["said"]
    return said(_last_user_message(state["messages"]) or HumanMessage(""))


def _last_user_message(messages: list[BaseMessage]) -> HumanMessage | None:
    last = messages[-1] if messages else None
    return last if isinstance(last, HumanMessage) else None


def _label(thread_id: str, titles: dict[str, str]) -> str:
    return _shortened(f"Continue in {titles.get(thread_id, 'a conversation')}", _OPTION_CHARS) if thread_id else _NEW


def _shortened(text: str, chars: int) -> str:
    line = " ".join(text.split())
    return line if len(line) <= chars else line[: chars - 1] + "…"
