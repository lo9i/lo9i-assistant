"""The send_message tool: messages the agent starts itself, on a channel other than this chat."""

from datetime import UTC, datetime

from langchain_core.tools import tool
from langgraph.prebuilt import ToolRuntime

from assistant.core.context import Context, require_store
from assistant.core.conversation import sent
from assistant.core.outbox import DeliveryError
from assistant.core.tools.registry import register


@register("messages")
@tool
async def send_message(text: str, channel: str, runtime: ToolRuntime[Context]) -> str:
    """Send the user a message on a chat channel, for example a reminder on Telegram. Use it in
    scheduled jobs to reach the user, or when asked to message them somewhere. `channel`: one of the
    chat channels listed under Channels in the system prompt (not cli, web or worker)."""
    outbox = runtime.context.outbox
    if outbox is None:
        return "Messages can't be sent from here."
    try:
        await outbox.send(channel, text)
    except DeliveryError as e:
        return str(e)
    # Sent from this channel's own conversation, it's already in its history.
    if channel != runtime.context.channel:
        await sent.record(require_store(runtime.store), runtime.context.user_id, channel, text, datetime.now(UTC))
    return f"Sent on {channel}."
