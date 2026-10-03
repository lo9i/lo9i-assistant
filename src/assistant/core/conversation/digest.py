"""Digests an archived part of the conversation: summaries plus memory extraction (D3).

One structured-output call returns everything, so an epoch change costs one model call.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field

from assistant.core.conversation import prompts
from assistant.core.llm import build_structured
from assistant.core.llm.choice import ModelChoice
from assistant.core.memory.facts import Fact
from assistant.core.memory.facts import render as render_facts
from assistant.core.memory.profile import Profile


class EpochDigest(BaseModel):
    episode_summary: str = Field(description="Summary of the transcript only: topics, decisions, outcomes.")
    conversation_summary: str = Field(
        description="Running summary of the previous summary plus the transcript: what the assistant needs to "
        "continue the conversation, including open tasks and commitments."
    )
    profile: Profile = Field(description="The full updated user profile.")
    new_facts: list[str] = Field(description="One-off facts worth remembering that are not saved yet.")
    outdated_fact_ids: list[str] = Field(description="Ids of saved facts the transcript shows are wrong or outdated.")


@dataclass
class DigestInput:
    previous_summary: str
    profile: Profile
    facts: list[Fact]
    transcript: str


Digester = Callable[[DigestInput], Awaitable[EpochDigest]]

_PROMPT = prompts.load("digest")


def build_digester(choice: ModelChoice) -> Digester:
    llm = build_structured(choice, choice.worker_model, EpochDigest)

    async def _digest(data: DigestInput) -> EpochDigest:
        return EpochDigest.model_validate(await llm.ainvoke([HumanMessage(_prompt(data))]))

    return _digest


def _prompt(data: DigestInput) -> str:
    return _PROMPT.format(
        previous_summary=data.previous_summary or "(none)",
        profile=data.profile.model_dump_json(indent=2),
        facts=render_facts(data.facts),
        transcript=data.transcript,
    )
