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
    interrupt_id: str
    request: dict[str, Any]


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


Event = TextDelta | ToolStarted | ToolFinished | ApprovalRequired | Transcribed | Done | Error
