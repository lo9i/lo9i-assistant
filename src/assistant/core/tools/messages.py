"""The send_message tool: messages the agent starts itself, on a channel other than this chat."""

from datetime import UTC, datetime

from langchain_core.tools import tool
from langgraph.prebuilt import ToolRuntime
from langgraph.store.base import BaseStore

from assistant.core import inbox
from assistant.core.channels.chat import threads as chat_threads
from assistant.core.context import Context, require_store, thread_of
from assistant.core.conversation import sent
from assistant.core.outbox import DeliveryError
from assistant.core.repositories import offers
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
        sent_ids = await outbox.send(channel, text)
    except DeliveryError as e:
        return await _not_installed(require_store(runtime.store), channel) or str(e)
    store, user_id = require_store(runtime.store), runtime.context.user_id
    # Replying to it goes on in this conversation; a scheduled job's isn't written in again.
    if not runtime.context.unattended:
        await chat_threads.record_own(store, user_id, channel, sent_ids, thread_of(runtime.config))
    # Sent from the conversation the channel last wrote in, it's already in its history.
    if await inbox.channel_thread(store, user_id, channel) != thread_of(runtime.config):
        await sent.record(store, user_id, channel, text, datetime.now(UTC))
    return f"Sent on {channel}."


async def _not_installed(store: BaseStore, channel: str) -> str:
    """Points to offer_plugin when the channel is a plugin the extras have but this computer doesn't."""
    if channel not in {o.name for o in await offers.offerable(store)}:
        return ""
    return f"{channel} isn't installed. Offer it to the user with offer_plugin."
