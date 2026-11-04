"""Telling a background subagent's end (core/background.py): its answer, or what went wrong, goes back to the
conversation it works for, in the turn header of the user's next message there, and the assistant follows it up at
once, unasked, so the answer is used while the user may be away; the user gets a notification, a toast in every app,
and a message on the chat channel the conversation was on. One the user stopped is only noted for the assistant:
the user knows already."""

from lo9i.core.background import Ended, short
from lo9i.core.background_subagents.records import DONE, STOPPED, BackgroundSubagent
from lo9i.core.i18n import said

# How much of the task the user's notification and the assistant's note show, and of the answer the notification.
_ASKED_NOTICE, _ASKED_NOTE, _RESULT_NOTICE = 60, 200, 300


def note_key(subagent_id: str) -> str:
    """Its turn header note (core/conversation/ended.py)."""
    return f"subagent:{subagent_id}"


def ended(subagent: BackgroundSubagent) -> Ended:
    asked = short(subagent.task, _ASKED_NOTE)
    note = f'The background subagent {subagent.id}, asked "{asked}", is {subagent.status}'
    if subagent.status == STOPPED:
        note += ": the user stopped it before it answered"
    elif subagent.result:
        # Whole: it's what the assistant sent it off for.
        note += f". Its answer:\n{subagent.result}" if subagent.status == DONE else f": {subagent.result}"
    ok = subagent.status == DONE
    return Ended(note_key(subagent.id), ok, _notice(subagent), note, follow_up=ok)


def _notice(subagent: BackgroundSubagent) -> str:
    """One the user stopped isn't told to them."""
    asked, result = short(subagent.task, _ASKED_NOTICE), short(subagent.result, _RESULT_NOTICE)
    if subagent.status == DONE:
        return said("✅ A subagent finished ({asked}): {result}", asked=asked, result=result)
    return said("⚠️ A subagent failed ({asked}): {result}", asked=asked, result=result)
