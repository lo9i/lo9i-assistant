"""Transport-neutral events streamed from the service to gateways."""

from dataclasses import dataclass
from typing import Any


@dataclass
class TextDelta:
    text: str


@dataclass
class ToolStarted:
    name: str
    args: dict[str, Any]


@dataclass
class ToolFinished:
    name: str
    output: str


@dataclass
class ApprovalRequired:
    """The run waits for the user. Usually an approval, answered with {"approved", "reason"}; a
    request whose `kind` is QUESTION is a question with options (core/tools/questions.py), with
    `question`, `options` and `multiple`, answered with {"choices": [picked options]}."""

    interrupt_id: str
    request: dict[str, Any]


QUESTION = "question"


def is_question(request: dict[str, Any]) -> bool:
    return request.get("kind") == QUESTION


@dataclass
class Transcribed:
    """A voice message was transcribed; gateways show it so the user can catch mistakes."""

    text: str
    language: str


@dataclass
class Done:
    pass


@dataclass
class Error:
    message: str


@dataclass
class Cancelled:
    """The user stopped the run before it finished."""


Event = TextDelta | ToolStarted | ToolFinished | ApprovalRequired | Transcribed | Done | Error | Cancelled
