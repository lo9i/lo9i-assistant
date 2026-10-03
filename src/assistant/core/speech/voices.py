"""Kokoro voices offered for spoken replies. A voice speaks one language."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Voice:
    id: str
    name: str
    language: str
    # espeak language code Kokoro phonemizes with.
    lang: str


VOICES = [
    Voice("af_heart", "Heart", "English (US)", "en-us"),
    Voice("af_bella", "Bella", "English (US)", "en-us"),
    Voice("am_michael", "Michael", "English (US)", "en-us"),
    Voice("bf_emma", "Emma", "English (UK)", "en-gb"),
    Voice("bm_george", "George", "English (UK)", "en-gb"),
    Voice("ef_dora", "Dora", "Spanish", "es"),
    Voice("em_alex", "Alex", "Spanish", "es"),
    Voice("pf_dora", "Dora", "Portuguese (BR)", "pt-br"),
    Voice("pm_alex", "Alex", "Portuguese (BR)", "pt-br"),
    Voice("ff_siwis", "Siwis", "French", "fr-fr"),
    Voice("if_sara", "Sara", "Italian", "it"),
    Voice("im_nicola", "Nicola", "Italian", "it"),
    Voice("hf_alpha", "Alpha", "Hindi", "hi"),
]
_BY_ID = {v.id: v for v in VOICES}
# The voice used until the user picks one, by the first voice-message language.
_DEFAULTS = {"es": "ef_dora", "pt": "pf_dora", "fr": "ff_siwis", "it": "if_sara", "hi": "hf_alpha"}


def voice(voice_id: str) -> Voice | None:
    return _BY_ID.get(voice_id)


def default_voice(languages: list[str]) -> str:
    return _DEFAULTS.get(languages[0], "af_heart") if languages else "af_heart"
