"""The apps' own text in the language chosen (core/language.py). Text is written in English where it's used, and
each other language has a table, a JSON file mapping the English text to its translation: the English is the key,
as with gettext, so the code reads as it did. `{name}` placeholders are filled after the lookup. Text kept before
it's shown (a list of commands) is marked with `translatable` and translated where it's shown. A text a table
lacks shows in English; the tests fail on one (tests/core/test_i18n.py). The terminal app has tables of its own,
read the same way (assistant_terminal/i18n.py)."""

import json
from collections.abc import Mapping
from pathlib import Path

from langgraph.store.base import BaseStore

from assistant.core import language
from assistant.core.language import Shown


class Texts:
    def __init__(self, language: Shown, table: Mapping[str, str]) -> None:
        self.language: Shown = language
        self._table = table

    def __call__(self, text: str, /, **values: object) -> str:
        translated = self._table.get(text, text)
        return translated.format(**values) if values else translated

    def number(self, value: float) -> str:
        """A whole number grouped by thousands as the language writes it: 2,361 or 2.361."""
        grouped = f"{value:,.0f}"
        return grouped.replace(",", ".") if self.language == "es" else grouped


def translatable(text: str) -> str:
    """Marks text translated later, where it's shown."""
    return text


def read_tables(folder: Path) -> dict[Shown, dict[str, str]]:
    """The tables in `folder`, one <language>.json each; English needs none. Read once, when the module that
    has them is imported."""
    return {"en": {}, "es": json.loads((folder / "es.json").read_text(encoding="utf-8"))}


_TABLES = read_tables(Path(__file__).parent)


def texts(language: Shown) -> Texts:
    """The core's text (what the chat channels show) in `language`."""
    return Texts(language, _TABLES[language])


async def chosen(store: BaseStore) -> Texts:
    """The core's text in the language the user chose, English for auto."""
    return texts(language.shown(await language.load(store)))
