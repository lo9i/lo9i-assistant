"""What's said in a live voice call, kept in its conversation as it's said: the user's words as the call's
transcription heard them, a user message with a turn header (via voice), and the voice's as it spoke them, an
assistant message; both marked as said in the call. History shows them; no model call sends them (`without_spoken`):
the assistant learns what was said from the notes its requests from the call come with (notes.py), so the messages a
model reads keep alternating as every provider requires. Which are left out depends only on the messages, which are
only ever appended, so every call sends the same ones before the new ones and the prompt cache keeps hitting."""

from collections.abc import Sequence
from datetime import datetime

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from assistant.core.conversation.turn_header import header_block
from assistant.core.voice.heard import Line

# The channel a call's messages and its requests to the assistant come from (the turn header's "via voice").
VOICE_CHANNEL = "voice"
# The mark, in a user message's additional_kwargs or an assistant message's response_metadata, no model call sends.
SPOKEN = "lo9i_voice_call"


def message(line: Line, at: datetime) -> BaseMessage:
    if line.who == "voice":
        return AIMessage(line.text, response_metadata={SPOKEN: True})
    content: list[str | dict] = [header_block(VOICE_CHANNEL, at), {"type": "text", "text": line.text}]
    return HumanMessage(content, additional_kwargs={SPOKEN: True})


def is_spoken(message: BaseMessage) -> bool:
    marks = message.response_metadata if isinstance(message, AIMessage) else message.additional_kwargs
    return bool(marks.get(SPOKEN))


def without_spoken(messages: Sequence[BaseMessage]) -> list[BaseMessage]:
    return [m for m in messages if not is_spoken(m)]
