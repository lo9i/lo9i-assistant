"""Transport-neutral events streamed from the service to gateways."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TextDelta:
    text: str


@dataclass
class Thinking:
    """A handed-off agent's reasoning (core/agent_tasks/steps.py), shown apart from its reply."""

    text: str


@dataclass
class ToolStarted:
    name: str
    args: dict[str, Any]
    # The tool call's id, so a subagent's tools can name the delegate call they belong to.
    id: str = field(default="", compare=False)
    # The id of the delegate call whose subagent made this call; empty for the agent's own calls.
    within: str = ""


@dataclass
class ToolFinished:
    name: str
    output: str
    # As in ToolStarted.
    within: str = ""


@dataclass
class ApprovalRequired:
    """The run waits for the user. Usually an approval, answered with {"approved", "reason"}; a
    request whose `kind` is QUESTION is a question with options (core/tools/questions.py), with
    `question`, `options` and `multiple`, answered with {"choices": [picked options]}. One whose
    `kind` is PLUGIN_OFFER offers a plugin from the extras (core/tools/plugins.py), with `name`,
    `description` and the plugin as the repository lists it (`server` or `skill`): the app installs
    it through its usual route and answers {"installed": bool}. One whose `kind` is SIDE_CONVERSATION
    suggests moving a task out of home (core/tools/side.py), with `title`, `brief` and
    `first_message`: it's answered {"moved": bool}, and on yes the client starts a side conversation
    once this run ends and sends `first_message` there. One whose `kind` is PLUGIN_SETUP opens
    an installed plugin's setup (its email accounts, a channel's pairing), with `name`, `description`
    and `server`, answered with {"done": true} once the user closes it."""

    interrupt_id: str
    request: dict[str, Any]


QUESTION = "question"


def is_question(request: dict[str, Any]) -> bool:
    return request.get("kind") == QUESTION


PLUGIN_OFFER = "plugin"


def is_plugin_offer(request: dict[str, Any]) -> bool:
    return request.get("kind") == PLUGIN_OFFER


PLUGIN_SETUP = "plugin_setup"


def is_plugin_setup(request: dict[str, Any]) -> bool:
    return request.get("kind") == PLUGIN_SETUP


SIDE_CONVERSATION = "side_conversation"


def is_side_conversation(request: dict[str, Any]) -> bool:
    return request.get("kind") == SIDE_CONVERSATION


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


Event = TextDelta | Thinking | ToolStarted | ToolFinished | ApprovalRequired | Transcribed | Done | Error | Cancelled
