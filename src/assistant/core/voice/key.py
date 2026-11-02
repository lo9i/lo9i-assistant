"""The OpenAI API key live voice calls use: the one saved for them in Settings → Audio, kept encrypted
(core/secret_store.py); else the model's own key when the model is OpenAI's API (Settings → Model, or .env); else
.env's OPENAI_API_KEY when it's for OpenAI's API. The main model can be any provider's: only the voice needs OpenAI."""

from dataclasses import dataclass
from typing import Literal

from langgraph.store.base import BaseStore

from assistant.core import secret_store
from assistant.core.config import settings
from assistant.core.llm.choice import ModelChoice
from assistant.core.secret_store import SecretBox, SecretError

_REF = "voice_calls_openai_key"

# Where the key in use comes from; "" when there's none, and calls can't be made.
Source = Literal["saved", "model", "env", ""]


@dataclass(frozen=True)
class VoiceKey:
    value: str
    source: Source


async def current(store: BaseStore, box: SecretBox, model: ModelChoice) -> VoiceKey:
    """A saved key that can't be read any more (the key file changed) counts as none, so the app asks again."""
    try:
        saved = await secret_store.get(store, box, _REF)
    except SecretError:
        saved = ""
    if saved:
        return VoiceKey(saved, "saved")
    if model.provider == "openai" and not model.values.get("base_url") and model.values.get("api_key"):
        return VoiceKey(model.values["api_key"], "model")
    if settings.openai_api_key and not settings.openai_base_url:
        return VoiceKey(settings.openai_api_key, "env")
    return VoiceKey("", "")


async def save(store: BaseStore, box: SecretBox, key: str) -> None:
    await secret_store.put(store, box, _REF, key)


async def clear(store: BaseStore) -> None:
    await secret_store.delete(store, _REF)
