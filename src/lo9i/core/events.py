"""Transport-neutral events streamed from the service to gateways."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


def _now() -> str:
    return datetime.now(UTC).isoformat()


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
    # When it started, as ISO 8601: the apps show it on the call, and replaying the run keeps it.
    at: str = field(default_factory=_now, compare=False)


@dataclass
class ToolFinished:
    name: str
    output: str
    # As in ToolStarted.
    within: str = ""


@dataclass
class SubagentProgress:
    """How the subagent of the delegate call `within` is doing, after each of its model calls
    (core/subagent.py): its model calls so far, of `max_steps`; the tokens its last call took, against its
    model's window (0 when not known); and when it started, as ISO 8601. The apps show it as the call's status line."""

    within: str
    steps: int
    max_steps: int
    context_tokens: int
    context_limit: int
    started_at: str


@dataclass
class UserSaid:
    """A message the user sent an agent the conversation is handed to while it worked
    (core/agent_tasks/steps.py), shown among its steps where it was passed on."""

    text: str
    # The names of the files sent with it.
    files: list[str] = field(default_factory=list)
    # The message's id in the task's inbox; "" for one the worker didn't pass on.
    id: str = field(default="", compare=False)
    # The agent gets to it only once it's done with what it's doing: a UserTaken event with its id says when.
    # One still waiting when the run ends wasn't taken, and goes to the agent as the next message.
    waiting: bool = False


@dataclass
class UserTaken:
    """The agent got to a message the user sent it that was waiting (UserSaid.waiting)."""

    id: str


@dataclass
class UserWithdrawn:
    """A message the user sent an agent that was waiting (UserSaid.waiting) was taken back before the agent got to it:
    removed, or edited, which sends its new text as a message of its own (AgentTasks.withdraw)."""

    id: str


@dataclass
class ApprovalRequired:
    """The run waits for the user. Usually an approval, answered with {"approved", "reason"}; a
    request whose `kind` is QUESTION is a question with options (core/tools/questions.py), with
    `question`, `options` and `multiple`, answered with {"choices": [picked options]}. One whose
    `kind` is PLUGIN_OFFER offers a plugin from the extras (core/tools/plugins.py), with `name`,
    `description` and the plugin as the repository lists it (`server` or `skill`): the app installs
    it through its usual route and answers {"installed": bool}. One whose `kind` is PLUGIN_SETUP
    opens an installed plugin's setup (its email accounts, a channel's pairing), with `name`,
    `description` and `server`, answered with {"done": true} once the user says it's done (hiding the
    dialog answers nothing). One whose `kind` is FORM is an MCP server's form for the user, or a link it
    asks the user to open (core/mcp/elicitation.py), answered with {"action": "accept" | "decline" |
    "cancel", "content": {...}}."""

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


FORM = "form"


def is_form(request: dict[str, Any]) -> bool:
    return request.get("kind") == FORM


# Why an approval was rejected when the user wrote again instead of answering it.
MOVED_ON = "the user sent a new message instead of answering"


def declined(request: dict[str, Any]) -> dict[str, Any]:
    """The answer to `request` when the user moved on without answering it (sent a new message): an approval
    rejected, a question skipped, a plugin not installed, a setup closed, a server's form declined."""
    if is_form(request):
        return {"action": "decline"}
    if is_question(request):
        return {"choices": None}
    if is_plugin_offer(request):
        return {"installed": False}
    if is_plugin_setup(request):
        return {"done": True}
    return {"approved": False, "reason": MOVED_ON}


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
    conversation shows before it (core/conversation/carried.py); "" for none. `brief`: for a coding task the
    assistant moved out, the agent it's for, so clients show it as the task and not the user's message
    (core/conversation/briefs.py); "" for the user's own."""

    id: str
    thread_id: str
    title: str
    text: str
    line: str
    carried: str = ""
    brief: str = ""


@dataclass
class Held:
    """lo9i is installing an update: the run was kept instead of run (core/conversation/held.py), and runs once
    lo9i is back on it, announced with this `id` (`held` in its `run` event), so a client that showed the user's
    message then doesn't show it twice. Each client says so in its own words, in the user's language."""

    id: str


@dataclass
class Done:
    pass


@dataclass
class Error:
    message: str
    # A spending limit was reached (core/usage/budget.py): the run stopped there, as the message says.
    over_budget: bool = False


@dataclass
class Cancelled:
    """The user stopped the run before it finished."""


Event = (
    TextDelta
    | Thinking
    | ToolStarted
    | ToolFinished
    | SubagentProgress
    | UserSaid
    | UserTaken
    | UserWithdrawn
    | ApprovalRequired
    | Transcribed
    | Dispatched
    | Held
    | Done
    | Error
    | Cancelled
)
