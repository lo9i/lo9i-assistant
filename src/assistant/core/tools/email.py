"""The send_email tool. Recipients outside the allowlist need approval (denied in scheduled runs)."""

from langchain_core.tools import tool
from langgraph.prebuilt import ToolRuntime

from assistant.core.context import Context, require_store
from assistant.core.integrations import email
from assistant.core.integrations.email import EmailError
from assistant.core.skills import store as skills
from assistant.core.tools.approval import ask
from assistant.core.tools.registry import register


@register("email")
@tool
async def send_email(to: list[str], subject: str, body: str, runtime: ToolRuntime[Context]) -> str:
    """Send a plain-text email from the user's configured address. `to` is a list of addresses."""
    config = await email.load(require_store(runtime.store))
    if not config.connected:
        return f"Email isn't set up. Load the {skills.SETUP} skill and give the user its steps for email."
    outsiders = [a for a in to if not config.allowed(a)]
    if outsiders:
        request = {
            "tool": "send_email",
            "command": f"To: {', '.join(to)}\nSubject: {subject}",
            "reason": f"email to {', '.join(outsiders)}",
        }
        rejection = ask(request, runtime.context)
        if rejection:
            return rejection
    try:
        await email.send(config, to, subject, body)
    except EmailError as e:
        return str(e)
    return f"Sent to {', '.join(to)}."
