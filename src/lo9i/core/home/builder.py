"""Builds one Home section: the worker model reads the plugins' tools the section may use, then its findings are
put in the section's format (model.py).

Two steps, so every provider can do it: gathering (core/gathering.py) with the section's tools says what it found,
then the structured model (core/llm/build_structured) writes that as items, which pydantic validates. Only read-only
tools are offered, and only those run, so building Home never changes anything and never waits for an approval."""

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_core.runnables import Runnable

from lo9i.core.config import settings
from lo9i.core.context import UNATTENDED_CHANNEL, Context
from lo9i.core.conversation import prompts
from lo9i.core.gathering import Gatherer, build_gatherer
from lo9i.core.graph import McpTools
from lo9i.core.home.model import HomeSection, SectionContent
from lo9i.core.llm import build_structured
from lo9i.core.llm.choice import ModelChoice
from lo9i.core.storage import Storage
from lo9i.core.usage.meter import TokenMeter


class SectionBuilder:
    def __init__(self, gatherer: Gatherer, structured: Runnable[list[BaseMessage], Any]) -> None:
        self._gatherer = gatherer
        self._structured = structured

    async def build(
        self, user_id: str, section: HomeSection, tools: list[dict[str, Any]], now: datetime
    ) -> SectionContent:
        """Raises what the model calls raise, and a validation error for an answer that doesn't fit the format."""
        task = _task(section, now)
        found = await self._gatherer.gather(Context(user_id, UNATTENDED_CHANNEL), prompts.load("home"), task, tools)
        message = HumanMessage(f"{task}\n\nWhat was found:\n{found}")
        content = await self._structured.ainvoke([SystemMessage(prompts.load("home_format")), message])
        return SectionContent.model_validate(content)


def build_section_builder(storage: Storage, choice: ModelChoice, mcp: McpTools) -> SectionBuilder:
    meter = TokenMeter(storage.usage, "home")
    gatherer = build_gatherer(storage, choice, mcp, meter)
    return SectionBuilder(gatherer, build_structured(choice, choice.worker_model, SectionContent, meter))


def _task(section: HomeSection, now: datetime) -> str:
    local = now.astimezone(ZoneInfo(settings.timezone))
    return f"Now: {local:%a %Y-%m-%d %H:%M %Z}.\nSection: {section.title}\n\n{section.prompt}"
