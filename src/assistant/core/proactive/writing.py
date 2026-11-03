"""The models the briefing and the reviews use, all on the worker model so the user's day costs little: gathering from
the plugins' read-only tools and the user's mail (core/gathering.py), then one structured call that writes the briefing
or the review, which pydantic validates. Rebuilt with the model (core/agent/model.py). Recorded in the token ledger as
`proactive`."""

from dataclasses import dataclass
from typing import Any

from langchain_core.messages import BaseMessage
from langchain_core.runnables import Runnable

from assistant.core.gathering import Gatherer, build_gatherer
from assistant.core.graph import McpTools
from assistant.core.llm import build_structured
from assistant.core.llm.choice import ModelChoice
from assistant.core.proactive.model import BriefingDraft, ReviewDraft
from assistant.core.storage import Storage
from assistant.core.tools.email import search_email
from assistant.core.usage.meter import TokenMeter

# The assistant's own tools gathering may run, offered while an email account can be read.
MAIL_TOOLS = (search_email,)


@dataclass(frozen=True)
class ProactiveModels:
    gatherer: Gatherer
    briefing: Runnable[list[BaseMessage], Any]
    review: Runnable[list[BaseMessage], Any]


def build_proactive_models(storage: Storage, choice: ModelChoice, mcp: McpTools) -> ProactiveModels:
    meter = TokenMeter(storage.usage, "proactive")
    return ProactiveModels(
        gatherer=build_gatherer(storage, choice, mcp, meter, MAIL_TOOLS),
        briefing=build_structured(choice, choice.worker_model, BriefingDraft, meter),
        review=build_structured(choice, choice.worker_model, ReviewDraft, meter),
    )
