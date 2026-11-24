"""Messages the user sends the same way each time, for the same skill, go to that skill's home conversation.

Each message the inbox sends on (dispatch_nodes.py) is kept with its kind (`kind_of`): the channel it came from,
what it carried (an image, a link, a voice note, or nothing) and its caption, the text the user typed, lowercase
and trimmed. Once its run ends where it went, the outcome is the one skill that handled it (`handled_by`: a
use_skill call's skill, or the plugin whose tools it called, a plugin's skill counting as its plugin), or none
when it used none or several. When the latest HABIT_RUNS outcomes of a message's kind (same channel, same thing
carried, the same caption or either without one) all ended in the same skill, that's a habit: the message goes to
the skill's home conversation without the model, made the first time and again if the user deleted it, titled
after the skill and never retitled (`Conversation.home_of`). A message that still lands in a new conversation and
ends in a skill with a home is moved there afterwards (core/agent/skill_homes.py), and so, by the nightly review, is
a conversation of the day whose every exchange used only that skill.

One Store record per message sent on under ("routing_outcomes", user_id), the latest _KEPT."""

import re
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolCall
from langgraph.store.base import BaseStore

from lo9i.core import conversations
from lo9i.core.conversation.turn_header import is_header
from lo9i.core.conversations import Conversation
from lo9i.core.speech.voice import is_voice_block

HABIT_RUNS = 3
_KEPT = 500
IMAGE, LINK, VOICE = "image", "link", "voice"
_URL = re.compile(r"https?://\S+", re.IGNORECASE)


@dataclass(frozen=True)
class Kind:
    channel: str
    # IMAGE, VOICE, LINK, or "" for text alone.
    carried: str
    caption: str

    def matches(self, other: "Kind") -> bool:
        same_caption = self.caption == other.caption or not self.caption or not other.caption
        return self.channel == other.channel and self.carried == other.carried and same_caption


def kind_of(message: HumanMessage, channel: str) -> Kind:
    blocks = message.content if isinstance(message.content, list) else [{"type": "text", "text": message.content}]
    typed = [str(b.get("text", "")) for b in blocks if isinstance(b, dict) and _typed(b)]
    text = " ".join(typed)
    if any(is_voice_block(b) for b in blocks):
        carried = VOICE
    elif any(_is_image(b) for b in blocks):
        carried = IMAGE
    else:
        carried = LINK if _URL.search(text) else ""
    return Kind(channel, carried, " ".join(_URL.sub(" ", text).lower().split()))


async def expect(store: BaseStore, user_id: str, dispatch_id: str, kind: Kind) -> None:
    """The message sent on as `dispatch_id` is of `kind`; its outcome comes when its run ends (`ended`)."""
    value = {"at": datetime.now(UTC).isoformat(), "kind": asdict(kind), "skill": None}
    await store.aput(_namespace(user_id), dispatch_id, value)


async def ended(store: BaseStore, user_id: str, dispatch_id: str, skill: str) -> None:
    """The run of the message sent on as `dispatch_id` ended, handled by `skill` ("" for none, or several)."""
    item = await store.aget(_namespace(user_id), dispatch_id)
    if item is not None:
        await store.aput(_namespace(user_id), dispatch_id, item.value | {"skill": skill})


async def outcome(store: BaseStore, user_id: str, dispatch_id: str) -> str:
    """The skill that handled the message sent on as `dispatch_id`; "" for none, or while its run hasn't ended."""
    item = await store.aget(_namespace(user_id), dispatch_id)
    return str(item.value.get("skill") or "") if item else ""


async def habit(store: BaseStore, user_id: str, kind: Kind) -> str:
    """The skill the latest HABIT_RUNS messages of `kind` all ended in; "" when they didn't, or there are fewer."""
    items = sorted(await store.asearch(_namespace(user_id), limit=10_000), key=lambda i: i.value["at"], reverse=True)
    for item in items[_KEPT:]:
        await store.adelete(_namespace(user_id), item.key)
    ended_ = [i.value for i in items[:_KEPT] if i.value["skill"] is not None]
    alike = [v["skill"] for v in ended_ if kind.matches(Kind(**v["kind"]))][:HABIT_RUNS]
    return alike[0] if len(alike) == HABIT_RUNS and alike[0] and len(set(alike)) == 1 else ""


async def home(store: BaseStore, user_id: str, skill: str) -> Conversation | None:
    """The skill's home conversation; None when it has none (or the user deleted it)."""
    return next((c for c in await conversations.recent(store, user_id) if c.home_of == skill), None)


async def make_home(store: BaseStore, user_id: str, skill: str) -> Conversation:
    """A new home conversation for the skill, titled after it."""
    now = datetime.now(UTC).isoformat()
    made = Conversation(conversations.new_id(user_id), title(skill), now, now, titled=True, tags=[skill], home_of=skill)
    await conversations.save(store, user_id, made)
    return made


def title(skill: str) -> str:
    """ "watchlist" is "Watchlist", "open-loops" "Open loops"."""
    words = " ".join(skill.replace("-", " ").replace("_", " ").split())
    return words[:1].upper() + words[1:]


async def handled_by(
    messages: Sequence[BaseMessage], skill_plugin: Callable[[str], Awaitable[str]], plugin_of: Callable[[str], str]
) -> str:
    """The one skill the run's `messages` used, "" for none or several. `skill_plugin`: the plugin a skill comes
    with ("" for none); `plugin_of`: the plugin of a tool ("" for a core tool)."""
    used: set[str] = set()
    for message in messages:
        for call in message.tool_calls if isinstance(message, AIMessage) else []:
            used |= {await _skill(call, skill_plugin, plugin_of)} - {""}
    return used.pop() if len(used) == 1 else ""


def exchanges(messages: Sequence[BaseMessage]) -> list[list[BaseMessage]]:
    """The messages from each user message up to the next one; [] when there's none, or the last hasn't ended in a
    reply."""
    asked = [i for i, m in enumerate(messages) if isinstance(m, HumanMessage)]
    last = messages[-1] if messages else None
    if not asked or not isinstance(last, AIMessage) or last.tool_calls:
        return []
    return [list(messages[start:end]) for start, end in zip(asked, [*asked[1:], len(messages)], strict=True)]


async def _skill(call: ToolCall, skill_plugin: Callable[[str], Awaitable[str]], plugin_of: Callable[[str], str]) -> str:
    if call["name"] == "use_skill":
        name = str(call["args"].get("name", ""))
        return await skill_plugin(name) or name
    return plugin_of(call["name"])


def _typed(block: Any) -> bool:
    return (
        isinstance(block, dict) and block.get("type") == "text" and not is_header(block) and not is_voice_block(block)
    )


def _is_image(block: Any) -> bool:
    if not isinstance(block, dict):
        return False
    upload = block.get("value", {}).get("upload", {}) if block.get("type") == "non_standard" else {}
    return block.get("type") == "image" or str(upload.get("media_type", "")).startswith("image/")


def _namespace(user_id: str) -> tuple[str, ...]:
    return ("routing_outcomes", user_id)
