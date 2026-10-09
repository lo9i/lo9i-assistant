"""Matching a message in home to the side conversations it may continue (core/conversation/related.py)."""

from assistant.core.conversation.related import matches

_TAGS = {
    "ferro": ["ferro carril oeste", "ferro", "primera nacional", "fútbol", "football"],
    "boca": ["boca juniors", "fútbol", "football", "primera división"],
    "youtube": ["youtube", "audio download", "video"],
    "email": ["email", "ana", "gmail"],
    "telegram": ["telegram bot", "lo9i", "setup"],
    "expenses": ["expenses", "october", "budget", "lo9i"],
}


def test_a_rare_tag_word_matches_without_accents():
    assert matches("cuando juega Ferro?", _TAGS) == ["ferro"]
    assert matches("que tal la primera division?", _TAGS) == ["boca", "ferro"]


def test_more_shared_rare_words_rank_first():
    assert matches("download that youtube video's audio", _TAGS) == ["youtube"]
    assert matches("¿hay fútbol hoy? juega ferro", _TAGS)[:2] == ["ferro", "boca"]


def test_words_no_tag_uses_never_match():
    assert matches("what's the weather in the city", _TAGS) == []


def test_untagged_conversations_never_match():
    assert matches("ferro", {"a": [], "b": []}) == []
