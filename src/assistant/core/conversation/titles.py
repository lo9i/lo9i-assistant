"""Titles for the conversation list: a few words saying what a conversation is about, and tags (the
names and topics a later message about it would use), written by the worker model from what the user
and the assistant said."""

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass

from langchain_core.messages import BaseMessage, HumanMessage

from assistant.core.conversation import prompts
from assistant.core.conversation.display import shown
from assistant.core.llm import build_llm, metered
from assistant.core.llm.choice import ModelChoice
from assistant.core.usage.log import UsageLog
from assistant.core.usage.meter import TokenMeter


@dataclass(frozen=True)
class Titled:
    title: str
    tags: list[str]


Titler = Callable[[str], Awaitable[Titled]]

_PROMPT = prompts.load("title")
# A long conversation is titled from its beginning and its end, where its topic and outcome are.
_HALF = 4000
_TAGS = "tags:"
_MAX_TAGS = 12


def build_titler(choice: ModelChoice, usage: UsageLog) -> Titler:
    """Its calls are recorded in `usage` as titles."""
    llm = metered(build_llm(choice, choice.worker_model), TokenMeter(usage, "title"))

    async def _title(conversation: str) -> Titled:
        reply = await llm.ainvoke([HumanMessage(_PROMPT.format(conversation=conversation))])
        return _parse(reply.text)

    return _title


def conversation_text(messages: Sequence[BaseMessage]) -> str:
    """What was said, without tool calls and turn headers."""
    said = [f"{m.role.capitalize()}: {m.text}" for m in shown(messages) if m.role != "tool"]
    text = "\n\n".join(said)
    return text if len(text) <= 2 * _HALF else f"{text[:_HALF]}\n\n[…]\n\n{text[-_HALF:]}"


def _parse(reply: str) -> Titled:
    """The title is the first line; tags follow on a line starting with "Tags:"."""
    lines = [line.strip() for line in reply.splitlines() if line.strip()]
    tagged = next((line for line in lines if line.lower().startswith(_TAGS)), "")
    tags = [" ".join(t.split()).strip("\"'*#").lower() for t in tagged[len(_TAGS) :].split(",")]
    first = lines[0] if lines and lines[0] != tagged else ""
    return Titled(" ".join(first.split()).strip("\"'“”*# ").rstrip("."), [t for t in tags if t][:_MAX_TAGS])
