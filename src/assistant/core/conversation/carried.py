"""A quick exchange the inbox carries to a new conversation (core/conversation/dispatch_nodes.py), kept with
the message that followed it up. The model reads it in a turn header note; the apps show it before that
message, from the message's `additional_kwargs`, which no model call sends (core/conversation/display.py).
Each line is what the user or the assistant said, cut to a length."""

from collections.abc import Sequence
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from assistant.core.conversation import prompts
from assistant.core.conversation.turn_header import note_block, said

# The key in a user message's additional_kwargs.
CARRIED = "lo9i_carried"

# {"role": "user" | "assistant", "text": ...}
Line = dict[str, str]

_SPEAKERS = {"user": "User", "assistant": "Assistant"}
_SHOWN_SPEAKERS = {"user": "You", "assistant": "Assistant"}


def lines(messages: Sequence[BaseMessage], chars: int) -> list[Line]:
    """What the user and the assistant said, each cut to `chars`; tool calls and results left out."""
    found: list[Line] = []
    for message in messages:
        if isinstance(message, HumanMessage) and (text := said(message)):
            found.append({"role": "user", "text": _shortened(text, chars)})
        elif isinstance(message, AIMessage) and (text := message.text.strip()):
            found.append({"role": "assistant", "text": _shortened(text, chars)})
    return found


def transcript(carried: Sequence[Line]) -> str:
    """For the model: "User: …" and "Assistant: …", one per line."""
    return "\n".join(f"{_SPEAKERS[line['role']]}: {line['text']}" for line in carried)


def note(carried: Sequence[Line]) -> dict[str, str]:
    """The turn header note the new conversation's first message starts with."""
    return note_block(prompts.load("carried_from_inbox").format(exchange=transcript(carried)))


def shown(carried: Sequence[Line]) -> str:
    """For the apps: Markdown, one paragraph per line said."""
    return "\n\n".join(f"**{_SHOWN_SPEAKERS[line['role']]}:** {line['text']}" for line in carried)


def of(message: BaseMessage) -> list[Line]:
    """The exchange a message carries; none for most."""
    found: Any = message.additional_kwargs.get(CARRIED)
    return list(found) if isinstance(found, list) else []


def _shortened(text: str, chars: int) -> str:
    line = " ".join(text.split())
    return line if len(line) <= chars else line[: chars - 1] + "…"
