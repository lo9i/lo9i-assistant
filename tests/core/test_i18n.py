"""The daemon's text in each language: every text the code marks has a translation in each table, and the tables
hold nothing the code no longer marks."""

from pathlib import Path
from string import Formatter

import pytest
from langgraph.store.memory import InMemoryStore

from assistant.core import i18n, language
from assistant.core.i18n import read_tables, texts
from assistant.core.language import LanguageError
from tests.translations import marked_texts

_SPANISH = read_tables(Path(i18n.__file__).parent)["es"]


def test_every_marked_text_has_a_spanish_translation_and_none_is_left_over():
    marked = marked_texts(Path(i18n.__file__).parent.parent.parent)
    assert sorted(marked - _SPANISH.keys()) == []
    assert sorted(_SPANISH.keys() - marked) == []


def test_translations_keep_their_placeholders():
    assert [english for english, spanish in _SPANISH.items() if _fields(english) != _fields(spanish)] == []


def test_text_is_shown_in_the_language_and_filled_in():
    assert texts("es")("Unknown command /{command}.", command="x") == "Comando desconocido: /x."
    assert texts("en")("Unknown command /{command}.", command="x") == "Unknown command /x."
    assert texts("es")("A text no table has") == "A text no table has"


async def test_the_language_is_auto_until_chosen_and_auto_shows_english():
    store = InMemoryStore()
    assert await language.load(store) == "auto"
    assert (await i18n.chosen(store)).language == "en"
    assert await language.save(store, "es") == "es"
    assert (await i18n.chosen(store)).language == "es"
    with pytest.raises(LanguageError):
        await language.save(store, "fr")


def _fields(text: str) -> set[str]:
    return {name for _, name, _, _ in Formatter().parse(text) if name}
