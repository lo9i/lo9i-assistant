"""The send_message tool: messages the agent starts itself, on a channel other than this chat."""

from langchain_core.tools import tool
from langgraph.prebuilt import ToolRuntime

from assistant.core.context import Context
from assistant.core.outbox import DeliveryError
from assistant.core.tools.registry import register


@register("messages")
@tool
async def send_message(text: str, runtime: ToolRuntime[Context], channel: str = "telegram") -> str:
    """Send the user a message on another channel, for example a reminder on Telegram. Use it in
    scheduled jobs to reach the user, or when asked to message them somewhere. `channel`: telegram."""
    outbox = runtime.context.outbox
    if outbox is None:
        return "Messages can't be sent from here."
    try:
        await outbox.send(channel, text)
    except DeliveryError as e:
        return str(e)
    return f"Sent on {channel}."
