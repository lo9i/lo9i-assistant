"""The agent's suggestion to move a focused task out of the home conversation (the
suggest_side_conversation tool) as Move / Keep buttons, `sm:<interrupt id>` or `sk:<interrupt id>`.
On Move, the run is answered, then the channel goes to the side conversation (the one that exists, or a
new one) and the brief is sent there (conversations.py)."""

from typing import Any

from assistant.core.channels.chat.port import Buttons

_MOVE, _KEEP = "sm", "sk"


def side_text(request: dict[str, Any]) -> str:
    return f"{side_question(request)} {request.get('title', '')}\n\n{request.get('brief', '')}"


def side_question(request: dict[str, Any]) -> str:
    """Continuing a side conversation that exists, or starting one."""
    return "Continue in your side conversation?" if request.get("thread_id") else "Move to a side conversation?"


def side_buttons(interrupt_id: str) -> Buttons:
    return [("➡️ Move", f"{_MOVE}:{interrupt_id}"), ("Keep it here", f"{_KEEP}:{interrupt_id}")]


def parse_side(data: str) -> tuple[str, bool] | None:
    """(interrupt id, moved) from button data, or None if it isn't a side conversation button."""
    action, _, interrupt_id = data.partition(":")
    if action not in (_MOVE, _KEEP) or not interrupt_id:
        return None
    return interrupt_id, action == _MOVE
