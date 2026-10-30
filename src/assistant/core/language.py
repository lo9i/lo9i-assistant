"""The language of the apps' own text, chosen in Settings → General (/language in the terminal app): English,
Spanish, or auto, which follows each browser's language in the web app and is English where there's no browser
(the terminal app, the chat channels). One Store record; auto until the user picks one. Prompts stay in English
and the assistant replies in the language the user writes; speech follows it (core/speech/preferences.py)."""

from typing import Literal, cast, get_args

from langgraph.store.base import BaseStore

from assistant.core.said import said

_NAMESPACE = ("settings",)
_KEY = "language"

Language = Literal["auto", "en", "es"]
# The languages text is written in: auto settled.
Shown = Literal["en", "es"]

DEFAULT: Language = "auto"
_CHOICES = ", ".join(get_args(Language))


class LanguageError(ValueError):
    """A language that isn't one of the choices."""


async def load(store: BaseStore) -> Language:
    item = await store.aget(_NAMESPACE, _KEY)
    language = item.value.get("language", DEFAULT) if item else DEFAULT
    return cast(Language, language) if language in get_args(Language) else DEFAULT


async def save(store: BaseStore, language: str) -> Language:
    """Raises LanguageError."""
    if language not in get_args(Language):
        raise LanguageError(
            said("Unknown language: {language}. Choose one of: {choices}.", language=language, choices=_CHOICES)
        )
    await store.aput(_NAMESPACE, _KEY, {"language": language})
    return cast(Language, language)


def shown(language: Language) -> Shown:
    """The language text is shown in where no browser says one: English for auto."""
    return "en" if language == "auto" else language


def answered_in(language: Language, app_shows: str | None) -> Shown:
    """The language to answer an app's request in: the one it says it shows (the web app settles auto by the
    browser's), else the chosen one."""
    return cast(Shown, app_shows) if app_shows in get_args(Shown) else shown(language)
