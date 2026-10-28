"""Digests an archived part of the conversation into memory (D3): an episode summary, profile
updates and facts, in one structured-output call. It runs in the background, after the reply that
started the epoch, or when a conversation is left.

A transcript the model refuses as too large is digested in halves, as the running summary is (summary.py): the
second with what the first one's digest left (the profile, the facts, its episode as the conversation before),
and the two joined into one."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace

from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field, ValidationError

from assistant.core.conversation import prompts
from assistant.core.conversation.transcript import MIN_HALVED_CHARS, halves
from assistant.core.llm import build_structured
from assistant.core.llm.choice import ModelChoice
from assistant.core.llm.errors import too_large
from assistant.core.memory.facts import Fact
from assistant.core.memory.facts import render as render_facts
from assistant.core.memory.profile import Profile
from assistant.core.usage.log import UsageLog
from assistant.core.usage.meter import TokenMeter


class MemoryDigest(BaseModel):
    episode_summary: str = Field(description="Summary of the transcript only: topics, decisions, outcomes.")
    profile: Profile = Field(description="The full updated user profile.")
    new_facts: list[str] = Field(
        description="Lasting details about the user that are not saved yet, as the rules allow; usually none."
    )
    outdated_fact_ids: list[str] = Field(description="Ids of saved facts the transcript shows are wrong or outdated.")


@dataclass
class DigestInput:
    previous_summary: str
    profile: Profile
    facts: list[Fact]
    transcript: str


Digester = Callable[[DigestInput], Awaitable[MemoryDigest]]

_PROMPT = prompts.load("digest")


def build_digester(choice: ModelChoice, usage: UsageLog) -> Digester:
    """Its calls are recorded in `usage` as memory."""
    llm = build_structured(choice, choice.worker_model, MemoryDigest, TokenMeter(usage, "memory"))

    async def _digest(data: DigestInput) -> MemoryDigest:
        prompt = _prompt(data)
        try:
            return MemoryDigest.model_validate(await llm.ainvoke([HumanMessage(prompt)]))
        except ValidationError as e:
            # The model broke a limit (most often a profile section over MAX_ITEMS): asked once more with the error.
            retry = (
                f"{prompt}\n\nYour previous answer was rejected:\n{e}\nFix it: merge or drop items to fit the limits."
            )
            return MemoryDigest.model_validate(await llm.ainvoke([HumanMessage(retry)]))

    return _in_halves(_digest)


def _in_halves(digest: Digester) -> Digester:
    async def _digest(data: DigestInput) -> MemoryDigest:
        try:
            return await digest(data)
        except Exception as e:
            if not too_large(e) or len(data.transcript) < MIN_HALVED_CHARS:
                raise
        first_half, second_half = halves(data.transcript)
        first = await _digest(replace(data, transcript=first_half))
        second = await _digest(_after(data, first, second_half))
        return _joined(first, second)

    return _digest


# The ids the facts the first half's digest found go by in the second one's input, which has them unsaved.
_FOUND = "found-"


def _after(data: DigestInput, first: MemoryDigest, transcript: str) -> DigestInput:
    """The second half's input: the memory as the first half's digest left it."""
    kept = [fact for fact in data.facts if fact.id not in first.outdated_fact_ids]
    found = [Fact(f"{_FOUND}{i}", text) for i, text in enumerate(first.new_facts)]
    before = "\n\n".join(filter(None, [data.previous_summary, first.episode_summary]))
    return DigestInput(before, first.profile, [*kept, *found], transcript)


def _joined(first: MemoryDigest, second: MemoryDigest) -> MemoryDigest:
    """One digest of both halves. A fact the first found and the second shows outdated isn't saved."""
    outdated = set(second.outdated_fact_ids)
    found = [text for i, text in enumerate(first.new_facts) if f"{_FOUND}{i}" not in outdated]
    return MemoryDigest(
        episode_summary=f"{first.episode_summary}\n\n{second.episode_summary}",
        profile=second.profile,
        new_facts=[*found, *second.new_facts],
        outdated_fact_ids=[
            *first.outdated_fact_ids,
            *(i for i in second.outdated_fact_ids if not i.startswith(_FOUND)),
        ],
    )


def _prompt(data: DigestInput) -> str:
    return _PROMPT.format(
        previous_summary=data.previous_summary or "(none)",
        profile=data.profile.model_dump_json(indent=2),
        facts=render_facts(data.facts),
        transcript=data.transcript,
    )
