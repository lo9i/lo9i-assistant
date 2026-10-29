"""The terminal app's own text in the language chosen in any app (core/language.py): auto is English here, as
there's no browser to follow. Text is written in English where it's used and looked up in this package's tables
(locales/<language>.json), the way the core's is (core/i18n). main.py sets the language from the daemon before
the app's modules are imported, since their key bindings and labels are made then; the app sets it again when
the setting changes, for what it shows after. The tests fail on a text a table lacks
(tests/terminal/test_i18n.py)."""

from datetime import date, datetime
from pathlib import Path

from assistant.core.i18n import Texts, read_tables, translatable
from assistant.core.language import Language, Shown, shown

__all__ = ["day_names", "decimal", "language", "number", "short_date", "t", "translatable", "use"]

_TABLES = read_tables(Path(__file__).parent / "locales")


class _Shown:
    """The language text is shown in, for the whole app: one terminal app runs per process."""

    texts = Texts("en", _TABLES["en"])


def use(language: Language) -> None:
    chosen = shown(language)
    _Shown.texts = Texts(chosen, _TABLES[chosen])


def language() -> Shown:
    return _Shown.texts.language


def t(text: str, /, **values: object) -> str:
    """`text` in the language shown, its {placeholders} filled from `values`."""
    return _Shown.texts(text, **values)


def number(value: float) -> str:
    """A whole number grouped by thousands as the language writes it: 2,361 or 2.361."""
    return _Shown.texts.number(value)


def decimal(value: float) -> str:
    """One decimal, with the language's decimal mark: 4.2 or 4,2."""
    written = f"{value:.1f}"
    return written.replace(".", ",") if _Shown.texts.language == "es" else written


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
_DAY_NAMES = [
    translatable("Monday"),
    translatable("Tuesday"),
    translatable("Wednesday"),
    translatable("Thursday"),
    translatable("Friday"),
    translatable("Saturday"),
    translatable("Sunday"),
]


def short_date(moment: date | datetime) -> str:
    """ "Wed 30 Sep", with the time after it for a datetime: "Wed 30 Sep 09:00"; "mié 30 sep" in Spanish."""
    day = f"{t(_WEEKDAYS[moment.weekday()])} {moment.day:02d} {t(_MONTHS[moment.month - 1])}"
    return f"{day} {moment:%H:%M}" if isinstance(moment, datetime) else day


def day_names(text: str) -> str:
    """`text` with the English names of the days of the week in it in the language shown (a cron schedule in
    words, whose library names them in English)."""
    for name in _DAY_NAMES:
        text = text.replace(name, t(name))
    return text
