"""Conversations a message in the inbox may continue. Each conversation has tags the model wrote with its
title (core/conversation/titles.py): the names and topics it's about. A message is matched against them:
a tag counts when all its words are in the message, so "about you" needs both, and a word few
conversations' tags use counts more. The matches come first among the conversations routing chooses from
(core/conversation/dispatch.py)."""

import math
import re
import unicodedata
from collections import Counter
from collections.abc import Mapping, Sequence

_MIN_WORD_CHARS = 3
_MATCHES = 3


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
