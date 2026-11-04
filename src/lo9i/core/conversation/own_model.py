"""The model a conversation answers with when the user picked one for it, instead of the main model (Settings →
Model). A Store record per conversation: the model's id and name, with the provider it belongs to, so a conversation
whose provider was changed since goes back to the main model.

Changing it in a conversation with messages appends a mark to it: an assistant message with no text, the model in
`response_metadata`, which no model call sends (`without_marks`) and history shows as a note (display.py). The next
user message then starts a new epoch at itself with everything before summarized (graph.py), so the model the
conversation changed to doesn't get the earlier messages, only their summary in its system prompt."""

from collections.abc import Sequence
from dataclasses import asdict, dataclass
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage
from langgraph.store.base import BaseStore

MODEL_CHANGED = "lo9i_model_changed"


@dataclass(frozen=True)
class OwnModel:
    provider: str
    # The provider's id for it, and the name the provider lists it with.
    model: str
    name: str


def _namespace(user_id: str) -> tuple[str, ...]:
    return ("conversation_models", user_id)


async def load(store: BaseStore, user_id: str, thread_id: str) -> OwnModel | None:
    item = await store.aget(_namespace(user_id), thread_id)
    return OwnModel(**item.value) if item else None


async def save(store: BaseStore, user_id: str, thread_id: str, own: OwnModel | None) -> None:
    """None: back to the main model."""
    if own is None:
        await forget(store, user_id, thread_id)
    else:
        await store.aput(_namespace(user_id), thread_id, asdict(own))


async def forget(store: BaseStore, user_id: str, thread_id: str) -> None:
    await store.adelete(_namespace(user_id), thread_id)


async def for_run(store: BaseStore, user_id: str, thread_id: str, provider: str) -> str:
    """The id of the model the conversation picked, "" for the main model: none picked, or one of another provider."""
    own = await load(store, user_id, thread_id)
    return own.model if own is not None and own.provider == provider else ""


def mark(name: str) -> AIMessage:
    """`name`: the model the conversation changed to, as the note says it."""
    return AIMessage("", response_metadata={MODEL_CHANGED: {"name": name}})


def of(message: BaseMessage) -> dict[str, Any] | None:
    """The mark's model, or None for any other message."""
    found = message.response_metadata.get(MODEL_CHANGED) if isinstance(message, AIMessage) else None
    return found if isinstance(found, dict) else None


def changed_since(messages: Sequence[BaseMessage], start: int) -> bool:
    """The model was changed after message `start`, where the epoch starts."""
    return any(of(m) is not None for m in messages[start:])


def without_marks(messages: Sequence[BaseMessage]) -> list[BaseMessage]:
    return [m for m in messages if of(m) is None]
