"""The CLI's slash commands, listed once for the command menu, /help and the plain REPL."""

from collections.abc import Sequence
from dataclasses import dataclass

from assistant.core.agent import Agent
from assistant_terminal.i18n import t, translatable


@dataclass(frozen=True)
class Command:
    name: str
    usage: str
    # In English, marked for translation: `text` is what shows.
    description: str

    @property
    def takes_argument(self) -> bool:
        return self.usage != self.name

    @property
    def text(self) -> str:
        """What it does, in the language shown."""
        return t(self.description)


# What /get-to-know-me sends: the get-to-know-you skill starts from it.
GET_TO_KNOW_ME = "Get to know me."

COMMANDS = [
    Command("/clear", "/clear", translatable("Start a new conversation")),
    Command(
        "/close",
        "/close",
        translatable("Close this conversation and show the one opened before it; a reply running keeps going"),
    ),
    Command("/conversations", "/conversations", translatable("Your conversations, newest first, to open one")),
    Command("/open", "/open", translatable("The conversations open here and any other working, to switch (Ctrl+O)")),
    Command("/inbox", "/inbox", translatable("Back to the inbox: the next message goes where it belongs")),
    Command("/move", "/move", translatable("Move the last message the inbox sent on to another conversation")),
    Command("/notifications", "/notifications", translatable("Job results and background work that ended")),
    Command("/home", "/home", translatable("Home: what the assistant gathered from your plugins, by section")),
    Command("/attach", "/attach <path>", translatable("Attach a file to the next message")),
    Command("/plugins", "/plugins", translatable("Install, update and remove plugins from the extras")),
    Command("/skills", "/skills", translatable("Browse, install and delete skills")),
    Command("/import-skills", "/import-skills", translatable("Import Claude Code's and Codex's skills")),
    Command("/files", "/files", translatable("Files you sent in your conversations")),
    Command(
        "/folder",
        "/folder",
        translatable("The folder this conversation is handed to, and what changed there; else your home folder"),
    ),
    Command("/jobs", "/jobs", translatable("Scheduled jobs")),
    Command("/usage", "/usage", translatable("Tool and skill usage")),
    Command("/logs", "/logs", translatable("The daemon's log, followed live if you like")),
    Command(
        "/doctor",
        "/doctor",
        translatable("The daemon's health check: what went wrong, by cause, and the starting context"),
    ),
    Command("/sessions", "/sessions", translatable("Clients connected to the daemon")),
    Command("/devices", "/devices", translatable("Browsers allowed in over the network")),
    Command("/model", "/model", translatable("The model provider, key and models")),
    Command("/audio", "/audio", translatable("Speech to text and spoken replies")),
    Command("/websearch", "/websearch", translatable("Web search: the Brave Search API key")),
    Command("/email", "/email", translatable("Who the assistant emails without asking, from any account")),
    Command("/mcp", "/mcp", translatable("MCP servers and their tools")),
    Command("/keys", "/keys", translatable("Keys and tokens removed plugins left kept, to delete them")),
    Command("/startup", "/startup", translatable("Start the assistant at boot")),
    Command("/host", "/host", translatable("The computer the assistant runs on")),
    Command("/name", "/name <name>", translatable("Rename the assistant")),
    Command(
        "/language",
        "/language [auto|en|es]",
        translatable("The language of the apps' own text; alone, the one in use"),
    ),
    Command(
        "/prompt", "/prompt", translatable("Edit the system prompt: persona, operating instructions, channel hints")
    ),
    Command(
        "/pin", "/pin [skill]", translatable("Keep a skill's instructions on for this conversation; alone, list them")
    ),
    Command("/unpin", "/unpin <skill>", translatable("Turn a pinned skill off for this conversation")),
    Command("/profile", "/profile", translatable("What the assistant knows about you: add, edit and remove")),
    Command("/get-to-know-me", "/get-to-know-me", translatable("Let the assistant get to know you")),
    Command("/mouse", "/mouse [on|off]", translatable("Turn clicking in the app on or off")),
    Command("/help", "/help", translatable("Show commands and keys")),
    Command("/quit", "/quit", translatable("Exit")),
]


def agent_commands(agents: Sequence[Agent]) -> list[Command]:
    """The commands installed plugins' agents add (/claude), leaving out any that would hide a built-in one."""
    built_in = {c.name for c in COMMANDS}
    return [
        Command(
            f"/{a.command}",
            f"/{a.command} [folder] | off",
            t(
                "Talk to {agent} directly, in a folder (alone it lets you pick one); off goes back to the assistant",
                agent=a.name,
            ),
        )
        for a in agents
        if f"/{a.command}" not in built_in
    ]


def matching(prefix: str, extra: Sequence[Command] = ()) -> list[Command]:
    return [c for c in [*COMMANDS, *extra] if c.name.startswith(prefix)]


def help_lines(extra: Sequence[Command] = ()) -> list[str]:
    shown = [*COMMANDS, *extra]
    width = max(len(c.usage) for c in shown)
    return [f"{c.usage.ljust(width)}   {c.text}" for c in shown]
