"""The language of the apps' own text, from any client (Settings → General, /language)."""

from assistant.core import i18n, language
from assistant.core.agent.base import ServiceBase
from assistant.core.i18n import Texts
from assistant.core.language import Language, LanguageError

__all__ = ["Language", "LanguageError", "LanguageMixin"]


class LanguageMixin(ServiceBase):
    async def language(self) -> Language:
        return await language.load(self._storage.store)

    async def set_language(self, chosen: str) -> Language:
        """Raises LanguageError."""
        return await language.save(self._storage.store, chosen)

    async def texts(self) -> Texts:
        """The core's text in the language chosen, English for auto: what the chat channels show."""
        return await i18n.chosen(self._storage.store)
