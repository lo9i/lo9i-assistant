"""An MCP server's form (core/mcp/elicitation.py) in a chat, which has no form to fill in: a link to open, or a form
with nothing to fill in, comes with the approval buttons (approved accepts it, rejected declines it); one with fields
says what it asks and to answer it in the app, where the conversation shows it, or to skip it by writing again."""

from typing import Any

from assistant.core.channels.chat.approvals import approval_buttons
from assistant.core.channels.chat.port import Buttons
from assistant.core.i18n import Texts


def form_text(t: Texts, request: dict[str, Any]) -> str:
    asked = t("{server} asks:", server=request.get("asked_by", "")) + f" {request.get('message', '')}"
    if url := request.get("url"):
        return f"{asked}\n\n{url}\n\n" + t("Open the link, then Approve; Reject declines it.")
    fields = [f"- {f.get('title') or f.get('key')}" for f in request.get("fields") or []]
    if not fields:
        return asked
    hint = t("Fill it in in the app, where this conversation shows it. Writing here again skips it.")
    return "\n\n".join([asked, "\n".join(fields), hint])


def form_buttons(t: Texts, interrupt_id: str, request: dict[str, Any]) -> Buttons:
    return [] if request.get("fields") else approval_buttons(t, interrupt_id)
