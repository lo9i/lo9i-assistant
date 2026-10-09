"""Side conversations a message in home may continue. Each conversation has tags the model wrote
with its title (core/conversation/titles.py): the names and topics it's about. A message in home is
matched against the side conversations' tags by the words they share, counting only words few
conversations' tags use, and the best are ranked first. The matches go in the message's turn header
for the assistant, which judges whether the message is about one of them and suggests continuing
there (core/tools/side.py)."""

import math
import re
import unicodedata
from collections import Counter
from collections.abc import Mapping, Sequence

from langgraph.store.base import BaseStore

from assistant.core import conversations, home
from assistant.core.conversation import prompts
from assistant.core.conversation.search import MessageIndex
from assistant.core.conversation.turn_header import note_block
from assistant.core.conversations import Conversation

# A word counts when the tags of at most this share of the side conversations use it (or _MIN_SHARED).
_RARE_SHARE = 0.2
_MIN_SHARED = 3
_MIN_WORD_CHARS = 3
_MATCHES = 3
_OPENING_CHARS = 200


async def notes(store: BaseStore, search: MessageIndex, user_id: str, thread_id: str, text: str) -> list[dict]:
    """The turn header note naming the side conversations `text` may continue, when it's sent in home."""
    home_id = await home.current(store, user_id)
    if not text.strip() or thread_id != home_id:
        return []
    sides = {c.thread_id: c for c in await conversations.recent(store, user_id) if c.thread_id != home_id}
    openings = await search.first_user_messages(user_id, list(sides))
    found = matches(text, {t: c.tags for t, c in sides.items()})
    if not found:
        return []
    listed = "\n".join(_line(sides[t], openings.get(t, "")) for t in found)
    return [note_block(prompts.load("related_side").format(conversations=listed))]


def matches(text: str, tags: Mapping[str, Sequence[str]]) -> list[str]:
    """The ids of the conversations whose tags share the most rare words with `text`, best first."""
    tagged = {t: set().union(*map(_words, found)) for t, found in tags.items()}
    used = Counter(w for words in tagged.values() for w in words)
    limit = max(_MIN_SHARED, len(tags) * _RARE_SHARE)
    rare = {w for w in _words(text) if 0 < used[w] <= limit}
    scores = {t: sum(math.log(len(tags) / used[w]) + 1 for w in rare & words) for t, words in tagged.items()}
    ranked = sorted((t for t, score in scores.items() if score > 0), key=lambda t: scores[t], reverse=True)
    return ranked[:_MATCHES]


def _words(text: str) -> set[str]:
    """Lowercase words without accents, so "Posición" matches "posicion"."""
    plain = unicodedata.normalize("NFKD", text.casefold())
    plain = "".join(c for c in plain if not unicodedata.combining(c))
    return {w for w in re.findall(r"\w+", plain) if len(w) >= _MIN_WORD_CHARS and not w.isdigit()}


def _line(conversation: Conversation, opening: str) -> str:
    line = " ".join(opening.split())
    line = line if len(line) <= _OPENING_CHARS else line[: _OPENING_CHARS - 1] + "…"
    tags = ", ".join(conversation.tags)
    return f'- {conversation.thread_id}: "{conversation.title}" ({tags}). It began: {line or "(unknown)"}'
