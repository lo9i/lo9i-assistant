"""Approval messages with Approve / Reject buttons. Button data is `a:<interrupt id>` or
`r:<interrupt id>` for the chat's own conversation, `ja:` or `jr:` for a scheduled job's run
(core/approvals.py)."""

from typing import Any

from assistant.core.channels.chat.port import Buttons
from assistant.core.i18n import Texts

_APPROVE, _REJECT = "a", "r"
_JOB_APPROVE, _JOB_REJECT = "ja", "jr"


def approval_text(t: Texts, request: dict[str, Any]) -> str:
    asked = t("Approve {tool}? ({reason})", tool=request.get("tool"), reason=request.get("reason"))
    return f"{asked}\n\n{request.get('command', request)}"


def approval_buttons(t: Texts, interrupt_id: str) -> Buttons:
    return [(t("✅ Approve"), f"{_APPROVE}:{interrupt_id}"), (t("❌ Reject"), f"{_REJECT}:{interrupt_id}")]


def parse_decision(data: str, place: str) -> tuple[str, dict[str, Any]] | None:
    """(interrupt id, decision) from button data, or None if it isn't an approval button. `place`
    names where a rejection happened, for example "Telegram"."""
    return _parse(data, _APPROVE, _REJECT, place)


def job_approval_text(t: Texts, title: str, request: dict[str, Any]) -> str:
    return f"{t('{title} is waiting for you.', title=title)}\n\n{approval_text(t, request)}"


def job_approval_buttons(t: Texts, interrupt_id: str) -> Buttons:
    return [(t("✅ Approve"), f"{_JOB_APPROVE}:{interrupt_id}"), (t("❌ Reject"), f"{_JOB_REJECT}:{interrupt_id}")]


def parse_job_decision(data: str, place: str) -> tuple[str, dict[str, Any]] | None:
    """Like `parse_decision`, for the buttons of a scheduled job's request."""
    return _parse(data, _JOB_APPROVE, _JOB_REJECT, place)


def _parse(data: str, approve: str, reject: str, place: str) -> tuple[str, dict[str, Any]] | None:
    action, _, interrupt_id = data.partition(":")
    if action not in (approve, reject) or not interrupt_id:
        return None
    approved = action == approve
    return interrupt_id, {"approved": approved, "reason": "" if approved else f"rejected in {place}"}
