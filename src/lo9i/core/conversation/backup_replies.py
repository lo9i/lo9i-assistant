"""A reply written by a backup model (core/llm/backups.py) when the conversation's model fails on the provider's side.
The backups are tried in order; the first that answers writes the reply, which starts with a short note naming it, so
the user knows. The note streams before the backup's words (a `TextDelta`, as the reply's own), and stays in the
reply's text, so history shows it as it showed live. A run notes it once per backup it switches to (`answered_by` in
graph state, cleared when a run starts).

The backup misses the prompt cache the main model built (another model or provider has its own); its calls are
metered as the main model's are, under the model that made them, so usage shows what each cost."""

import logging
from collections.abc import Awaitable, Callable

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langgraph.config import get_stream_writer
from langgraph.store.base import BaseStore

from lo9i.core.events import TextDelta
from lo9i.core.i18n import chosen
from lo9i.core.llm.backups import BackupModels
from lo9i.core.llm.errors import provider_failed

logger = logging.getLogger(__name__)

# Writes the reply with this model, from this provider (how it takes images, llm/providers.py).
Call = Callable[[BaseChatModel, str], Awaitable[BaseMessage]]


async def reply_with_backups(
    backups: BackupModels, store: BaseStore, failed_model: str, error: Exception, call: Call, noted: str
) -> tuple[BaseMessage, str]:
    """The reply of the first backup that answers and its name, after `failed_model` failed with `error`; that
    error again when none does. `noted`: the backup this run already said it answers with."""
    logger.warning("%s failed on the provider's side (%s); trying the backup models.", failed_model, error)
    note = ""
    for backup in await backups.after(failed_model):
        if backup.name != noted:
            note = await _note(store, failed_model, backup.name)
            get_stream_writer()(TextDelta(note))
        try:
            response = await call(backup.llm, backup.provider)
        except Exception as e:
            if not provider_failed(e):
                raise
            logger.warning("Backup model %s failed too (%s).", backup.name, e)
            noted = ""
            continue
        if backup.name != noted:
            response = _with_note(response, note)
        return response, backup.name
    raise error


async def _note(store: BaseStore, main: str, backup: str) -> str:
    t = await chosen(store)
    text = t("({main} isn't answering right now; the backup model {backup} answered.)", main=main, backup=backup)
    return text + "\n\n"


def _with_note(response: BaseMessage, note: str) -> BaseMessage:
    if not isinstance(response, AIMessage):
        return response
    content = response.content
    noted = note + content if isinstance(content, str) else [{"type": "text", "text": note}, *content]
    return response.model_copy(update={"content": noted})
