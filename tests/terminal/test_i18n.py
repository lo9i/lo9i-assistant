"""The terminal app's text in each language: every text it marks has a translation in each table, and the tables
hold nothing it no longer marks. A language picked with /language is used for what shows after."""

import ast
from datetime import datetime
from pathlib import Path
from string import Formatter

from textual.widgets._footer import FooterKey

import assistant_terminal
from assistant.core.i18n import read_tables
from assistant_terminal import i18n
from assistant_terminal.commands import COMMANDS, help_lines
from assistant_terminal.i18n import short_date, t
from assistant_terminal.tui.prompt import PromptInput
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


async def test_the_key_bindings_and_the_message_box_follow_a_language_change_at_once(app, client):
    async with app.run_test() as pilot:
        assert "New conversation" in _footer(app)
        await pilot.click("#prompt")
        await pilot.press(*"/language es", "enter")
        await wait_for(pilot, lambda: "Nueva conversación" in _footer(app))
        assert app.query_one(PromptInput).placeholder.startswith("Escríbele al asistente")


def test_no_text_is_translated_when_a_module_is_imported():
    """What's made at import (key bindings, lists of labels) would keep the language of the start."""
    assert [where for path in sorted(_PACKAGE.rglob("*.py")) for where in _translated_at_import(path)] == []


def _footer(app) -> list[str]:
    return [key.description for key in app.query(FooterKey)]


def _translated_at_import(path: Path) -> list[str]:
    tree = ast.parse(path.read_text())
    in_functions = {
        id(node)
        for function in ast.walk(tree)
        if isinstance(function, ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda)
        for node in ast.walk(function)
        if node is not function
    }
    return [
        f"{path.name}:{node.lineno}"
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "t"
        and id(node) not in in_functions
    ]


def _fields(text: str) -> set[str]:
    return {name for _, name, _, _ in Formatter().parse(text) if name}
