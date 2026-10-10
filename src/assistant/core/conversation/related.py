"""Side conversations a message in home may continue. Each conversation has tags the model wrote
with its title (core/conversation/titles.py): the names and topics it's about. A message in home is
matched against the side conversations' tags: a tag counts when all its words are in the message,
so "about you" needs both, and a word few conversations' tags use counts more. The matches go in
the message's turn header for the assistant, which judges whether the message is about one of them
and suggests continuing there (core/tools/side.py)."""

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
    """The ids of the conversations with tags whose words are all in `text`, best first: each word
    those tags cover weighs more the fewer conversations' tags use it. Ties keep `tags`' order."""
    said = _words(text)
    tagged = {t: [words for words in map(_words, found) if words] for t, found in tags.items()}
    used = Counter(w for found in tagged.values() for w in set().union(*found))
    covered = {t: set().union(*(words for words in found if words <= said)) for t, found in tagged.items()}
    scores = {t: sum(math.log(len(tags) / used[w]) + 1 for w in words) for t, words in covered.items()}
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
