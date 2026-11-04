"""What the assistant is told of a live voice call, in turn header notes, since no model call sends what's said in it
(spoken.py): each request from the call says it comes from one and what was said since the assistant's last answer
there; what was said after the last request is kept when the call ends and goes into the turn header of the next
message in its conversation, once."""

from collections.abc import Sequence
from datetime import UTC, datetime

from langgraph.store.base import BaseStore

from lo9i.core.attachments import Block
from lo9i.core.conversation import prompts
from lo9i.core.conversation.turn_header import note_block
from lo9i.core.voice.heard import Line

_WHO = {"user": "User", "voice": "Voice"}


def _namespace(user_id: str) -> tuple[str, ...]:
    return ("voice_call_unheard", user_id)


def request(said: Sequence[Line]) -> Block:
    """The note of a request from a call, with what was said since the assistant's last answer."""
    parts = [prompts.load("voice_call_request")]
    if said:
        parts.append(prompts.load("voice_call_said").format(said=transcript(said)))
    return note_block("\n\n".join(parts))


def transcript(lines: Sequence[Line]) -> str:
    return "\n".join(f"{_WHO[line.who]}: {line.text}" for line in lines)


async def keep(store: BaseStore, user_id: str, thread_id: str, said: Sequence[Line]) -> None:
    """What was said after the call's last request, which the assistant hasn't heard: for the next message there.
    Added to what an earlier call left, if the user hasn't written since."""
    if not said:
        return
    earlier = await store.aget(_namespace(user_id), thread_id)
    kept = [*(earlier.value["said"] if earlier else []), transcript(said)]
    await store.aput(_namespace(user_id), thread_id, {"said": kept, "at": datetime.now(UTC).isoformat()})


async def take(store: BaseStore, user_id: str, thread_id: str) -> list[Block]:
    """The note for the next message in the conversation, or nothing. It goes into one message only."""
    kept = await store.aget(_namespace(user_id), thread_id)
    if kept is None:
        return []
    await forget(store, user_id, thread_id)
    return [note_block(prompts.load("voice_call_ended").format(said="\n\n".join(kept.value["said"])))]


async def forget(store: BaseStore, user_id: str, thread_id: str) -> None:
    """For a deleted conversation too."""
    await store.adelete(_namespace(user_id), thread_id)
