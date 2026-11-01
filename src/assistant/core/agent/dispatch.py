"""How sure routing a message from the inbox has to be to continue a conversation, from any client
(Settings → Model, /model), and routing a new conversation's first message (core/conversation/first_message.py)."""

import logging
from collections.abc import Sequence

from assistant.core import inbox
from assistant.core.agent.base import ServiceBase
from assistant.core.attachments import Attachment
from assistant.core.conversation import dispatch_setting, first_message
from assistant.core.conversation.dispatch_setting import DispatchSetting
from assistant.core.speech import preferences
from assistant.core.speech.transcriber import TranscriptionError
from assistant.core.speech.voice import is_voice

logger = logging.getLogger(__name__)


class DispatchMixin(ServiceBase):
    async def dispatch_setting(self) -> DispatchSetting:
        return await dispatch_setting.load(self._storage.store)

    async def set_dispatch_setting(self, setting: DispatchSetting) -> DispatchSetting:
        """Applies from the next message. Raises DispatchSettingError."""
        return await dispatch_setting.save(self._storage.store, setting)

    async def route_first_message(self, user_id: str, text: str, files: Sequence[Attachment] = ()) -> str:
        """The conversation the first message of a new one continues, "" for none: by its text and what its voice
        recordings among `files` say, as the inbox routes a voice note."""
        message = "\n".join(filter(None, [text.strip(), *await self._heard(files)]))
        if not message:
            return ""
        store = self._storage.store
        inbox_id = await inbox.current(store, user_id) or ""
        search = self._storage.search
        return await first_message.place(self._classify, store, search, user_id, inbox_id, message, self._similar)

    async def _heard(self, files: Sequence[Attachment]) -> list[str]:
        """What the recordings say; one that can't be heard is left out, and the message is routed without it (it
        says why when it's sent)."""
        speech = await preferences.in_use(self._storage.store)
        heard = []
        for voice in filter(is_voice, files):
            try:
                transcript = await self._transcriber.transcribe(
                    voice.data, speech.model, speech.languages, speech.beam_size
                )
            except TranscriptionError:
                logger.warning("Couldn't hear a voice message to route it; it's routed by its text.", exc_info=True)
                continue
            heard.append(transcript.text)
        return heard
