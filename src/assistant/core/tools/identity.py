"""The rename_assistant tool, so the user can rename the assistant by asking."""

from langchain_core.tools import tool
from langgraph.prebuilt import ToolRuntime

from assistant.core import identity
from assistant.core.context import Context, require_store
from assistant.core.identity import InvalidNameError
from assistant.core.tools.registry import register


@register("identity")
@tool
async def rename_assistant(name: str, runtime: ToolRuntime[Context]) -> str:
    """Change your own name when the user asks you to (e.g. "call yourself Max"). The new name
    is used from the user's next message, and on Telegram."""
    try:
        saved = await identity.save_name(require_store(runtime.store), name)
    except InvalidNameError as e:
        return str(e)
    return f"Renamed to {saved}. It takes effect from the next message."
