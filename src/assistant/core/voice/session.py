"""A call's settings, sent with the browser's offer (realtime.py): the model, how it hears and speaks (in the voice
picked, voices.py), its instructions (prompts/voice_call.md) and its one tool, through which the assistant answers."""

from typing import Any

from assistant.core.voice.realtime import MODEL

ASK = "ask_assistant"
# Transcribes what the user says for the call's own events, which the browser shows and the conversation keeps
# (the model itself hears the audio).
_TRANSCRIPTION_MODEL = "gpt-4o-mini-transcribe"

_ASK_TOOL = {
    "type": "function",
    "name": ASK,
    "description": (
        "Ask the assistant you speak for, who has the user's memory, files, email, calendar, plugins and tools and "
        "the conversation this call is in. Use it for anything beyond small talk: questions about the user, their "
        "things or the world, and anything to look up, remember, plan or do. Its answer is what to tell the user."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "request": {
                "type": "string",
                "description": "What the user wants, in full, with the details they gave in the call.",
            }
        },
        "required": ["request"],
    },
}


def settings(instructions: str, voice: str) -> dict[str, Any]:
    """The call's session, as /v1/realtime/calls takes it."""
    return {
        "type": "realtime",
        "model": MODEL,
        "instructions": instructions,
        "audio": {
            "input": {"transcription": {"model": _TRANSCRIPTION_MODEL}, "turn_detection": {"type": "semantic_vad"}},
            "output": {"voice": voice},
        },
        "tools": [_ASK_TOOL],
        "tool_choice": "auto",
    }
