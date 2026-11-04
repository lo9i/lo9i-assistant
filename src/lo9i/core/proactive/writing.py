"""The model calls the briefing and the reviews make, on the worker model so the user's day costs little: one
structured call that picks the unread mail that matters (the briefing's only one, made only when there's unread mail),
and one that writes a review; pydantic validates both. Rebuilt with the model (core/agent/model.py). Recorded in the
token ledger as `proactive`."""

from dataclasses import dataclass
from typing import Any

from langchain_core.messages import BaseMessage
from langchain_core.runnables import Runnable

from lo9i.core.llm import build_structured
from lo9i.core.llm.choice import ModelChoice
from lo9i.core.proactive.model import MailDraft, ReviewDraft
from lo9i.core.storage import Storage
from lo9i.core.usage.meter import TokenMeter


@dataclass(frozen=True)
class ProactiveModels:
    mail: Runnable[list[BaseMessage], Any]
    review: Runnable[list[BaseMessage], Any]


def build_proactive_models(storage: Storage, choice: ModelChoice) -> ProactiveModels:
    meter = TokenMeter(storage.usage, "proactive")
    return ProactiveModels(
        mail=build_structured(choice, choice.worker_model, MailDraft, meter),
        review=build_structured(choice, choice.worker_model, ReviewDraft, meter),
    )
