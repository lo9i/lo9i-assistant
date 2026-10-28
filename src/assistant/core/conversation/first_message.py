"""Where the first message of a conversation a client opened for no topic goes (the web app's Chat in a new tab,
which never shows the inbox): on in the conversation it's about, picked as the inbox picks (dispatch.py), or
in the new one. Nothing is written anywhere: the client sends the message where it goes, so a message that
goes on elsewhere leaves the new conversation empty, and unlisted."""

import logging

from langgraph.store.base import BaseStore

from assistant.core.conversation import dispatch_setting
from assistant.core.conversation.dispatch import FOLLOW_UP, QUICK, Classifier, candidates
from assistant.core.conversation.meanings import SimilarConversations
from assistant.core.conversation.search import MessageIndex

logger = logging.getLogger(__name__)


async def place(
    classify: Classifier,
    store: BaseStore,
    search: MessageIndex,
    user_id: str,
    inbox_id: str,
    message: str,
    similar: SimilarConversations | None = None,
) -> str:
    """The id of the conversation `message` continues, or "" for the new one: with none to continue, a quick
    question, or the model less sure than the confidence setting."""
    found = await candidates(store, search, user_id, inbox_id, message, similar)
    if not found:
        return ""
    pick = await classify(message, found, "")
    sure = pick.confidence >= (await dispatch_setting.load(store)).confidence
    going = pick.place if sure and pick.place not in (QUICK, FOLLOW_UP) else ""
    logger.info("Routed a new conversation's first message to %s.", going or "itself")
    return going
