"""The ask_user tool: a question with options, answered with checkboxes in the web app, a selection
list in the terminal app, or buttons in Telegram and Slack. The run waits for the answer the way it
waits for an approval (core/events.py::ApprovalRequired)."""

from typing import Any

from langchain_core.tools import tool
from langgraph.prebuilt import ToolRuntime
from langgraph.types import interrupt

from assistant.core.context import Context
from assistant.core.events import QUESTION
from assistant.core.tools.registry import register

MAX_OPTIONS = 10
# Telegram and Slack buttons show about this much.
MAX_OPTION_LENGTH = 60


@register("messages")
@tool
async def ask_user(question: str, options: list[str], runtime: ToolRuntime[Context], multiple: bool = False) -> str:
    """Ask the user to pick from options, and wait for the answer. Use it when the choice is among
    known options (which sources to search, which of several matches is them); ask open questions in
    your reply instead. With `multiple`, the user can pick several options, or none. At most 10
    short options."""
    if problem := _problem(question, options):
        return f"Not asked: {problem}"
    if runtime.context.unattended:
        return "Not asked: nobody is watching this scheduled run. Go on without the answer, or report what you needed."
    answer = interrupt({"kind": QUESTION, "question": question, "options": options, "multiple": multiple})
    return _result(options, answer)


def _problem(question: str, options: list[str]) -> str:
    if not question.strip():
        return "the question is empty."
    if not options or len(options) > MAX_OPTIONS:
        return f"give between 1 and {MAX_OPTIONS} options."
    if len(set(options)) != len(options) or not all(o.strip() for o in options):
        return "options must be different and not empty."
    if any(len(o) > MAX_OPTION_LENGTH for o in options):
        return f"keep each option under {MAX_OPTION_LENGTH} characters."
    return ""


def _result(options: list[str], answer: Any) -> str:
    choices = answer.get("choices") if isinstance(answer, dict) else None
    if choices is None:
        return "The user closed the question without answering."
    picked = [o for o in options if o in choices]
    return f"The user picked: {'; '.join(picked)}." if picked else "The user picked none of the options."
