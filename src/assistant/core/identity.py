"""The assistant's name, chosen by the user. Stored as one Store record; empty means unnamed.

The system prompt tells the model its name, and a rename rebuilds the prompt at the next message
(core/graph.py). Chat channels hear about a rename (core/channels/hub.py): the Telegram bot
shows it as its display name.
"""

from langgraph.store.base import BaseStore

from assistant.core.i18n import said

_NAMESPACE = ("settings",)
_KEY = "assistant"
# Telegram's limit for a bot's display name.
MAX_LENGTH = 64


class InvalidNameError(Exception):
    pass


async def load_name(store: BaseStore) -> str:
    item = await store.aget(_NAMESPACE, _KEY)
    return item.value.get("name", "") if item else ""


async def save_name(store: BaseStore, name: str) -> str:
    """Saves and returns the cleaned name. Raises InvalidNameError."""
    name = " ".join(name.split())
    if not name:
        raise InvalidNameError(said("The name can't be empty."))
    if len(name) > MAX_LENGTH:
        raise InvalidNameError(said("Names can be up to {count} characters.", count=MAX_LENGTH))
    await store.aput(_NAMESPACE, _KEY, {"name": name})
    return name
