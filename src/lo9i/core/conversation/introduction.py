"""The one-time offer to get to know the user (the get-to-know-you skill). The user's first message
after setup decides it: when the profile holds nothing but what the apps' About you step asked (their name,
how to reply, what they want help with; core/memory/about_you.py), or nothing at all, a note in that
message's turn header asks the assistant to offer the rest. Either way a Store flag records that it was
decided, so it never comes back on its own; the user starts it again with /get-to-know-me, the button in
Settings, or by asking."""

from langgraph.store.base import BaseStore

from lo9i.core.context import UNATTENDED_CHANNEL
from lo9i.core.conversation import prompts
from lo9i.core.conversation.turn_header import note_block
from lo9i.core.memory import about_you, profile

_NAMESPACE = ("settings",)
_KEY = "get_to_know_you"


async def offer(store: BaseStore, user_id: str, channel: str) -> list[dict[str, str]]:
    """The note for the turn header, or nothing. Scheduled runs never count as the first message."""
    if channel == UNATTENDED_CHANNEL or await store.aget(_NAMESPACE, _KEY) is not None:
        return []
    await store.aput(_NAMESPACE, _KEY, {"offered": True})
    if not about_you.only_answers(await profile.load(store, user_id)):
        return []
    return [note_block(prompts.load("get_to_know_offer"))]
