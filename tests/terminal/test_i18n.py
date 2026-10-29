"""The terminal app's text in each language: every text it marks has a translation in each table, and the tables
hold nothing it no longer marks. A language picked with /language is used for what shows after."""

from datetime import datetime
from pathlib import Path
from string import Formatter

import assistant_terminal
from assistant.core.i18n import read_tables
from assistant_terminal import i18n
from assistant_terminal.commands import COMMANDS, help_lines
from assistant_terminal.i18n import short_date, t
from tests.terminal.conftest import wait_for
from tests.translations import marked_texts

_PACKAGE = Path(assistant_terminal.__file__).parent
_SPANISH = read_tables(_PACKAGE / "locales")["es"]


def test_every_marked_text_has_a_spanish_translation_and_none_is_left_over():
    marked = marked_texts(_PACKAGE)
    assert sorted(marked - _SPANISH.keys()) == []
    assert sorted(_SPANISH.keys() - marked) == []


def test_translations_keep_their_placeholders():
    assert [english for english, spanish in _SPANISH.items() if _fields(english) != _fields(spanish)] == []


def test_text_dates_and_commands_follow_the_language():
    moment = datetime(2026, 10, 28, 9, 5)
    assert short_date(moment) == "Wed 28 Oct 09:05"
    i18n.use("es")
    assert short_date(moment) == "mié 28 oct 09:05"
    assert t("Close") == "Cerrar"
    assert "Empezar una conversación nueva" in help_lines()[0]
    i18n.use("auto")
    assert t("Close") == "Close" and COMMANDS[0].text == "Start a new conversation"


async def test_language_command_says_and_sets_the_language(app, client):
    async with app.run_test() as pilot:
        await pilot.click("#prompt")
        await pilot.press(*"/language es", "enter")
        await wait_for(pilot, lambda: client.language.current == "es")
        assert t("Close") == "Cerrar"
        await pilot.press(*"/language fr", "enter")
        await wait_for(pilot, lambda: any("Unknown language" in n.message for n in app._notifications))
        assert client.language.current == "es"


def _fields(text: str) -> set[str]:
    return {name for _, name, _, _ in Formatter().parse(text) if name}
