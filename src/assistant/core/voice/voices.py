"""The voice live calls speak in, picked in Settings → Audio's Live voice calls card: one Store record, the
default until the user picks one. A call keeps the voice it started with: OpenAI doesn't change it once it spoke."""

from langgraph.store.base import BaseStore

from assistant.core.i18n import said

_NAMESPACE = ("settings",)
_KEY = "voice_calls"

# OpenAI's Realtime voices (https://developers.openai.com/api/docs/guides/realtime-conversations#voice-options),
# the ones it recommends for best quality first.
VOICES = ["marin", "cedar", "alloy", "ash", "ballad", "coral", "echo", "sage", "shimmer", "verse"]
DEFAULT = VOICES[0]


class VoiceChoiceError(Exception):
    """Not one of the voices."""


async def load(store: BaseStore) -> str:
    item = await store.aget(_NAMESPACE, _KEY)
    voice = item.value.get("voice", "") if item else ""
    return voice if voice in VOICES else DEFAULT


async def save(store: BaseStore, voice: str) -> None:
    """Raises VoiceChoiceError for a voice that isn't one of VOICES."""
    if voice not in VOICES:
        raise VoiceChoiceError(
            said("Unknown voice {voice}. Choose one of: {voices}.", voice=voice, voices=", ".join(VOICES))
        )
    await store.aput(_NAMESPACE, _KEY, {"voice": voice})
