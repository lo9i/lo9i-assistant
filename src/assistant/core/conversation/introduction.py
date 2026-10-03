"""The one-time offer to get to know the user (the get-to-know-you skill). The user's first message
after setup decides it: when the profile is still empty, a note in that message's turn header asks the
assistant to offer it. Either way a Store flag records that it was decided, so it never comes back on
its own; the user starts it again with /get-to-know-me, the button in Settings, or by asking."""

from langgraph.store.base import BaseStore

from assistant.core.context import UNATTENDED_CHANNEL
from assistant.core.conversation import prompts
from assistant.core.conversation.turn_header import note_block
from assistant.core.memory import profile

_NAMESPACE = ("settings",)
_KEY = "get_to_know_you"


async def offer(store: BaseStore, user_id: str, channel: str) -> list[dict[str, str]]:
    """The note for the turn header, or nothing. Scheduled runs never count as the first message."""
    if channel == UNATTENDED_CHANNEL or await store.aget(_NAMESPACE, _KEY) is not None:
        return []
    await store.aput(_NAMESPACE, _KEY, {"offered": True})
    current = await profile.load(store, user_id)
    if any(current.model_dump().values()):
        return []
    return [note_block(prompts.load("get_to_know_offer"))]
