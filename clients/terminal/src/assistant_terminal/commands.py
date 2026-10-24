"""The CLI's slash commands, listed once for the command menu, /help and the plain REPL."""

from collections.abc import Sequence
from dataclasses import dataclass

from assistant.core.agent import Agent


@dataclass(frozen=True)
class Command:
    name: str
    usage: str
    description: str

    @property
    def takes_argument(self) -> bool:
        return self.usage != self.name


# What /get-to-know-me sends: the get-to-know-you skill starts from it.
GET_TO_KNOW_ME = "Get to know me."

COMMANDS = [
    Command("/new", "/new", "Start a new conversation"),
    Command("/conversations", "/conversations", "Your conversations, newest first, to open one"),
    Command("/inbox", "/inbox", "Back to the inbox: the next message goes where it belongs"),
    Command("/move", "/move", "Move the last message the inbox sent on to another conversation"),
    Command("/notifications", "/notifications", "Job results and background work that ended"),
    Command("/attach", "/attach <path>", "Attach a file to the next message"),
    Command("/plugins", "/plugins", "Install, update and remove plugins from the extras"),
    Command("/skills", "/skills", "Browse, install and delete skills"),
    Command("/files", "/files", "Files you sent in your conversations"),
    Command("/jobs", "/jobs", "Scheduled jobs"),
    Command("/usage", "/usage", "Tool and skill usage"),
    Command("/logs", "/logs", "The daemon's log, followed live if you like"),
    Command("/sessions", "/sessions", "Clients connected to the daemon"),
    Command("/devices", "/devices", "Browsers allowed in over the network"),
    Command("/model", "/model", "The model provider, key and models"),
    Command("/audio", "/audio", "Speech to text and spoken replies"),
    Command("/websearch", "/websearch", "Web search: the Brave Search API key"),
    Command("/email", "/email", "Who the assistant emails without asking, from any account"),
    Command("/mcp", "/mcp", "MCP servers and their tools"),
    Command("/keys", "/keys", "Keys and tokens removed plugins left kept, to delete them"),
    Command("/startup", "/startup", "Start the assistant at boot"),
    Command("/host", "/host", "The computer the assistant runs on"),
    Command("/name", "/name <name>", "Rename the assistant"),
    Command("/prompt", "/prompt", "Edit the system prompt: persona, operating instructions, channel hints"),
    Command("/pin", "/pin [skill]", "Keep a skill's instructions on for this conversation; alone, list them"),
    Command("/unpin", "/unpin <skill>", "Turn a pinned skill off for this conversation"),
    Command("/profile", "/profile", "What the assistant knows about you: add, edit and remove"),
    Command("/get-to-know-me", "/get-to-know-me", "Let the assistant get to know you"),
    Command("/mouse", "/mouse [on|off]", "Turn clicking in the app on or off"),
    Command("/help", "/help", "Show commands and keys"),
    Command("/quit", "/quit", "Exit"),
]


def agent_commands(agents: Sequence[Agent]) -> list[Command]:
    """The commands installed plugins' agents add (/claude), leaving out any that would hide a built-in one."""
    built_in = {c.name for c in COMMANDS}
    return [
        Command(
            f"/{a.command}",
            f"/{a.command} [folder] | off",
            f"Talk to {a.name} directly, in a folder (alone it lets you pick one); off goes back to the assistant",
        )
        for a in agents
        if f"/{a.command}" not in built_in
    ]


def matching(prefix: str, extra: Sequence[Command] = ()) -> list[Command]:
    return [c for c in [*COMMANDS, *extra] if c.name.startswith(prefix)]


def help_lines(extra: Sequence[Command] = ()) -> list[str]:
    shown = [*COMMANDS, *extra]
    width = max(len(c.usage) for c in shown)
    return [f"{c.usage.ljust(width)}   {c.description}" for c in shown]
