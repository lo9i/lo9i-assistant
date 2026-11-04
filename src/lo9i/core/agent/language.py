"""The language of the apps' own text, from any client (Settings → General, /language)."""

from lo9i.core import i18n, language
from lo9i.core.agent.base import ServiceBase
from lo9i.core.i18n import Texts
from lo9i.core.language import Language, LanguageError

__all__ = ["Language", "LanguageError", "LanguageMixin"]


class LanguageMixin(ServiceBase):
    async def language(self) -> Language:
        return await language.load(self._storage.store)

    async def set_language(self, chosen: str) -> Language:
        """Raises LanguageError."""
        return await language.save(self._storage.store, chosen)

    async def texts(self, app_shows: str | None = None) -> Texts:
        """The core's text in the language chosen, English for auto: what the chat channels show. For an app's
        request, in the language it says it shows (`LANGUAGE_HEADER`), when it does."""
        return i18n.texts(language.answered_in(await language.load(self._storage.store), app_shows))
