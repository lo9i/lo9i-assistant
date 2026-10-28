"""The running summary of a conversation, rewritten when an epoch starts (D1): the new epoch's
system prompt carries it in place of the archived messages. Memory is digested apart, after the
reply (digest.py), so this call is all a new epoch waits for.

A transcript the model refuses as too large is summarized in halves, the second on top of the first's summary, as
a running summary is anyway."""

from collections.abc import Awaitable, Callable

from langchain_core.messages import HumanMessage

from assistant.core.conversation import prompts
from assistant.core.conversation.transcript import MIN_HALVED_CHARS, halves
from assistant.core.llm import build_llm, metered
from assistant.core.llm.choice import ModelChoice
from assistant.core.llm.errors import too_large
from assistant.core.usage.log import UsageLog
from assistant.core.usage.meter import TokenMeter

# The previous summary and the transcript being archived; returns the new summary.
Summarizer = Callable[[str, str], Awaitable[str]]

_PROMPT = prompts.load("summary")


def build_summarizer(choice: ModelChoice, usage: UsageLog) -> Summarizer:
    """Its calls are recorded in `usage` as summaries."""
    llm = metered(build_llm(choice, choice.worker_model), TokenMeter(usage, "summary"))

    async def _once(previous_summary: str, transcript: str) -> str:
        prompt = _PROMPT.format(previous_summary=previous_summary or "(none)", transcript=transcript)
        return (await llm.ainvoke([HumanMessage(prompt)])).text.strip()

    return _in_halves(_once)


def _in_halves(summarize: Summarizer) -> Summarizer:
    async def _summarize(previous_summary: str, transcript: str) -> str:
        try:
            return await summarize(previous_summary, transcript)
        except Exception as e:
            if not too_large(e) or len(transcript) < MIN_HALVED_CHARS:
                raise
        first, second = halves(transcript)
        return await _summarize(await _summarize(previous_summary, first), second)

    return _summarize
