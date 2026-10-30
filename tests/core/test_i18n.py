"""The daemon's text in each language: every text the code marks has a translation in each table, and the tables
hold nothing the code no longer marks."""

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from string import Formatter

import pytest
from langgraph.store.memory import InMemoryStore

from assistant.core import i18n, language
from assistant.core.i18n import holds_said, message, read_tables, said, texts
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


def test_an_error_said_reads_in_english_and_shows_in_the_language_asked():
    error = ValueError(said("{name} needs {label}.", name="gmail", label=said("API key")))
    assert str(error) == "gmail needs API key."
    assert texts("es").shown(error) == "gmail necesita Clave de API."
    assert texts("es").shown(KeyError("x")) == "'x'"
    wrapped = RuntimeError(said("{name}: {error}", name="claude", error=error))
    assert texts("es").shown(message(wrapped)) == "claude: gmail necesita Clave de API."


def test_said_text_within_an_answer_is_shown_in_the_language():
    @dataclass(frozen=True)
    class Answer:
        problems: list[str]
        by_name: dict[str, str]
        plain: str

    answer = Answer([said("Write a message or attach a file.")], {"x": said("Approved.")}, "as is")
    shown = texts("es").within(answer)
    assert shown == Answer(["Escribe un mensaje o adjunta un archivo."], {"x": "Aprobado."}, "as is")
    assert holds_said({"a": [said("x")]}) and not holds_said({"a": ["x"]})


def test_a_day_is_written_as_the_language_writes_it():
    assert texts("en").day(date(2026, 10, 28)) == "Wed 28 Oct"
    assert texts("es").day(date(2026, 10, 28)) == "mié 28 oct"
