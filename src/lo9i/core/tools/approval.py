"""Asking the user before a risky action. In unattended runs (scheduled jobs) the request goes to
the user's connected chat channels (core/approvals.py); otherwise nobody can answer, so the
action is denied and the denial is marked, so the job is recorded as needing attention."""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

from langgraph.types import interrupt

from lo9i.core.context import Context
from lo9i.core.events import MOVED_ON

# Appears in the tool result of every automatic denial; the scheduler looks for it.
UNATTENDED_DENIAL = "[denied: unattended run]"

# Set while a tool runs whose call the user already approved (core/untrusted.py): its own first ask passes.
_approved: ContextVar[bool] = ContextVar("approved", default=False)


@contextmanager
def approved() -> Iterator[None]:
    """The call made inside was approved: the first `ask` it makes isn't asked again. Later ones are (a server asking
    for text mid-call is another matter)."""
    token = _approved.set(True)
    try:
        yield
    finally:
        _approved.reset(token)


def ask(request: dict[str, Any], context: Context) -> str | None:
    """Pause for approval. Returns None if approved, or a message for the model if not."""
    if _approved.get():
        _approved.set(False)
        return None
    if context.unattended and not context.forwards_approvals:
        return (
            f"{UNATTENDED_DENIAL} Nobody is watching this scheduled run and no chat channel is connected, "
            f"so actions that need approval are denied: {request.get('reason')}."
        )
    decision = interrupt(request)
    if decision.get("approved"):
        return None
    return _rejected(decision.get("reason") or "no reason given")


def _rejected(reason: str) -> str:
    """What the model reads when the user said no: left at that, it went on with another way of doing the same."""
    if reason == MOVED_ON:
        return (
            f"The user rejected this ({reason}). Don't do it or anything else toward that request: answer their "
            "new message, and ask before doing more for the request."
        )
    return (
        f"The user rejected this ({reason}). Stop: don't try it another way or take any other action toward this "
        "request. Ask the user how they want to go on, and wait for their answer."
    )
