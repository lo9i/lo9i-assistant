"""The apps' own text in the language chosen (core/language.py). Text is written in English where it's used, and
each other language has a table, a JSON file mapping the English text to its translation: the English is the key,
as with gettext, so the code reads as it did. `{name}` placeholders are filled after the lookup. Text kept before
it's shown (a list of commands) is marked with `translatable` and translated where it's shown. An error's message
is written with `said`, which keeps its text and values for whoever shows it: the API in the language of the app
that asked (daemon/api.py), English in the log and for the model. A text a table lacks shows in English; the
tests fail on one (tests/core/test_i18n.py). The terminal app has tables of its own, read the same way
(assistant_terminal/i18n.py).

A third language takes a table in each place (this folder's, the terminal app's `locales/`, the web app's
`src/lib/locales/`), its code in core/language.py, and the cron library's locale for the terminal app's schedules
in words (`jobs_text.py::_CRON_LOCALES`); the chat channel plugins have tables of their own, in the extras."""

import dataclasses
import json
from collections.abc import Mapping
from datetime import date
from pathlib import Path
from typing import Any, cast

from langgraph.store.base import BaseStore

from assistant.core import language
from assistant.core.language import Shown
from assistant.core.said import Said, holds_said, message, said

__all__ = ["Said", "Texts", "chosen", "holds_said", "message", "read_tables", "said", "texts", "translatable"]


class Texts:
    def __init__(self, language: Shown, table: Mapping[str, str]) -> None:
        self.language: Shown = language
        self._table = table

    def __call__(self, text: str, /, **values: object) -> str:
        translated = self._table.get(text, text)
        return translated.format(**values) if values else translated

    def shown(self, value: object) -> str:
        """`value` in this language: a `said` text, an error raised with one, or else as it is."""
        if isinstance(value, Said):
            return self(value.text, **{name: self.shown(v) for name, v in value.values.items()})
        return self.shown(message(value)) if isinstance(value, BaseException) else str(value)

    def within(self, value: Any) -> Any:
        """`value` with the `said` texts in it shown in this language, through dataclasses, lists and dicts: what an
        API route returns."""
        if isinstance(value, Said):
            return self.shown(value)
        if dataclasses.is_dataclass(value) and not isinstance(value, type):
            changed = {f.name: self.within(getattr(value, f.name)) for f in dataclasses.fields(value) if f.init}
            return dataclasses.replace(value, **changed)
        if isinstance(value, list | tuple):
            return type(value)(self.within(item) for item in value)
        if isinstance(value, dict):
            return {key: self.within(item) for key, item in cast(dict[Any, Any], value).items()}
        return value

    def day(self, day: date) -> str:
        """ "Wed 28 Oct", or "mié 28 oct" in Spanish."""
        return f"{self(_WEEKDAYS[day.weekday()])} {day.day:02d} {self(_MONTHS[day.month - 1])}"

    def number(self, value: float) -> str:
        """A whole number grouped by thousands as the language writes it: 2,361 or 2.361."""
        grouped = f"{value:,.0f}"
        return grouped.replace(",", ".") if self.language == "es" else grouped


def translatable(text: str) -> str:
    """Marks text translated later, where it's shown."""
    return text


# Each marked one by one: the tests read the texts marked from the code.
_WEEKDAYS = [
    translatable("Mon"),
    translatable("Tue"),
    translatable("Wed"),
    translatable("Thu"),
    translatable("Fri"),
    translatable("Sat"),
    translatable("Sun"),
]
_MONTHS = [
    translatable("Jan"),
    translatable("Feb"),
    translatable("Mar"),
    translatable("Apr"),
    translatable("May"),
    translatable("Jun"),
    translatable("Jul"),
    translatable("Aug"),
    translatable("Sep"),
    translatable("Oct"),
    translatable("Nov"),
    translatable("Dec"),
]


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
