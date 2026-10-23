"""Transport-neutral events streamed from the service to gateways."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TextDelta:
    text: str


@dataclass
class Thinking:
    """A handed-off agent's reasoning (core/agent_tasks/steps.py), shown apart from its reply. It streams:
    Thinking events with nothing between them continue one another, like TextDelta."""

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
class UserSaid:
    """A message the user sent an agent the conversation is handed to while it worked
    (core/agent_tasks/steps.py), shown among its steps where it was passed on."""

    text: str


@dataclass
class ApprovalRequired:
    """The run waits for the user. Usually an approval, answered with {"approved", "reason"}; a
    request whose `kind` is QUESTION is a question with options (core/tools/questions.py), with
    `question`, `options` and `multiple`, answered with {"choices": [picked options]}. One whose
    `kind` is PLUGIN_OFFER offers a plugin from the extras (core/tools/plugins.py), with `name`,
    `description` and the plugin as the repository lists it (`server` or `skill`): the app installs
    it through its usual route and answers {"installed": bool}. One whose `kind` is PLUGIN_SETUP
    opens an installed plugin's setup (its email accounts, a channel's pairing), with `name`,
    `description` and `server`, answered with {"done": true} once the user closes it."""

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


@dataclass
class Transcribed:
    """A voice message was transcribed; gateways show it so the user can catch mistakes."""

    text: str
    language: str


@dataclass
class Dispatched:
    """The inbox sent the message on to a conversation (core/conversation/dispatch.py) instead of answering
    it, or the assistant moved work out of the inbox (core/tools/side.py). Once this run ends, the client
    that sent it goes to that conversation, `thread_id`, or starts a new one when it's empty, and sends the
    message there by its `id` (`send_dispatched`), files included. A message moved later
    (`move_dispatched`) comes with the id it was first sent on with. `title` names the conversation; `text`
    is what the message said, to show it; `line` is what the inbox records, which clients show for it.
    `carried` is the quick exchange in the inbox the message followed up, as Markdown, which its new
    conversation shows before it (core/conversation/carried.py); "" for none."""

    id: str
    thread_id: str
    title: str
    text: str
    line: str
    carried: str = ""


@dataclass
class Done:
    pass


@dataclass
class Error:
    message: str


@dataclass
class Cancelled:
    """The user stopped the run before it finished."""


Event = (
    TextDelta
    | Thinking
    | ToolStarted
    | ToolFinished
    | UserSaid
    | ApprovalRequired
    | Transcribed
    | Dispatched
    | Done
    | Error
    | Cancelled
)
