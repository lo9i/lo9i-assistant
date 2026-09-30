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


COMMANDS = [
    Command("/new", "/new", "Start a new conversation"),
    Command("/attach", "/attach <path>", "Attach a file to the next message"),
    Command("/skills", "/skills", "Browse and delete skills"),
    Command("/jobs", "/jobs", "Scheduled jobs"),
    Command("/usage", "/usage", "Tool and skill usage"),
    Command("/sessions", "/sessions", "Clients connected to the daemon"),
    Command("/telegram", "/telegram", "Connect Telegram"),
    Command("/email", "/email", "Connect email for sending"),
    Command("/startup", "/startup", "Start the assistant at boot"),
    Command("/name", "/name <name>", "Rename the assistant"),
    Command("/help", "/help", "Show commands and keys"),
    Command("/quit", "/quit", "Exit"),
]


def matching(prefix: str) -> list[Command]:
    return [c for c in COMMANDS if c.name.startswith(prefix)]


def help_lines() -> list[str]:
    width = max(len(c.usage) for c in COMMANDS)
    return [f"{c.usage.ljust(width)}   {c.description}" for c in COMMANDS]
