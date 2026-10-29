"""Sections built by code instead of the worker model, from what the daemon already knows (the Copilot plan's
allowance): they show even when the model can't answer. They're built in like the others (sections.py) and known
by their id, which a refresh looks up here before reaching for the model (refresh.py)."""

from typing import Protocol

from assistant.core.home.model import SectionContent


class CodedSection(Protocol):
    async def build(self) -> SectionContent: ...
