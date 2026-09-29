"""Approval messages with Approve / Reject buttons. Button data is `a:<interrupt id>` or `r:<interrupt id>`."""

from typing import Any

from assistant.gateways.telegram.port import Buttons

_APPROVE, _REJECT = "a", "r"


def approval_text(request: dict[str, Any]) -> str:
    return f"Approve {request.get('tool')}? ({request.get('reason')})\n\n{request.get('command', request)}"


def approval_buttons(interrupt_id: str) -> Buttons:
    return [("✅ Approve", f"{_APPROVE}:{interrupt_id}"), ("❌ Reject", f"{_REJECT}:{interrupt_id}")]


def parse_decision(data: str) -> tuple[str, dict[str, Any]] | None:
    """(interrupt id, decision) from button data, or None if it isn't an approval button."""
    action, _, interrupt_id = data.partition(":")
    if action not in (_APPROVE, _REJECT) or not interrupt_id:
        return None
    approved = action == _APPROVE
    return interrupt_id, {"approved": approved, "reason": None if approved else "rejected in Telegram"}
