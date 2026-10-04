"""The CLI's slash commands, listed once for the command menu, /help and the plain REPL."""

from dataclasses import dataclass


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
    Command("/conversations", "/conversations", "Earlier conversations, to resume one"),
    Command("/attach", "/attach <path>", "Attach a file to the next message"),
    Command("/plugins", "/plugins", "Install, update and remove plugins from the extras"),
    Command("/skills", "/skills", "Browse, install and delete skills"),
    Command("/files", "/files", "Files you sent in your conversations"),
    Command("/jobs", "/jobs", "Scheduled jobs"),
    Command("/usage", "/usage", "Tool and skill usage"),
    Command("/sessions", "/sessions", "Clients connected to the daemon"),
    Command("/devices", "/devices", "Browsers allowed in over the network"),
    Command("/model", "/model", "The model provider, key and models"),
    Command("/audio", "/audio", "Speech to text and spoken replies"),
    Command("/websearch", "/websearch", "Web search: the Brave Search API key"),
    Command("/mcp", "/mcp", "MCP servers and their tools"),
    Command("/startup", "/startup", "Start the assistant at boot"),
    Command("/name", "/name <name>", "Rename the assistant"),
    Command("/profile", "/profile", "What the assistant knows about you: add, edit and remove"),
    Command("/get-to-know-me", "/get-to-know-me", "Let the assistant get to know you"),
    Command("/mouse", "/mouse [on|off]", "Turn clicking in the app on or off"),
    Command("/help", "/help", "Show commands and keys"),
    Command("/quit", "/quit", "Exit"),
]


def matching(prefix: str) -> list[Command]:
    return [c for c in COMMANDS if c.name.startswith(prefix)]


def help_lines() -> list[str]:
    width = max(len(c.usage) for c in COMMANDS)
    return [f"{c.usage.ljust(width)}   {c.description}" for c in COMMANDS]
