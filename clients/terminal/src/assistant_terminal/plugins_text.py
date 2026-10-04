"""How plugins read in the terminal app: the list of what the extras offer, and one plugin's details."""

from dataclasses import dataclass

from assistant.core.agent import FoundServer, FoundSkill, RepositoryContents


@dataclass(frozen=True)
class Plugin:
    """A plugin the extras offer: an MCP server (maybe with its skill, a page or a chat channel), a chat
    channel, or a skill of its own."""

    name: str
    installed: bool
    server: FoundServer | None = None
    skill: FoundSkill | None = None

    @property
    def key(self) -> str:
        # A server and a skill can share a name.
        return f"{'server' if self.server else 'skill'}:{self.name}"

    @property
    def description(self) -> str:
        return self.server.description if self.server else self.skill.description if self.skill else ""

    @property
    def kind(self) -> str:
        """ "MCP server · channel · skill · page", "Channel" (a chat channel without tools), or "Skill"."""
        if self.server is None:
            return "Skill"
        only_channel = self.server.transport == "channel"
        parts = [
            ("Channel" if only_channel else "MCP server", True),
            ("channel", self.server.channel and not only_channel),
        ]
        parts += [("skill", self.server.skill), ("page", self.server.page)]
        return " · ".join(part for part, has in parts if has)


def version(plugin: Plugin) -> str:
    """The version installed, and the newer one the extras have ("1.0.0 → 1.1.0"); what the extras
    have when it isn't installed; "-" when none is declared."""
    found = plugin.server or plugin.skill
    available, here = (found.version, found.installed_version) if found else ("", "")
    if not plugin.installed:
        return available or "-"
    if available and available != here:
        return f"{here or '-'} → {available}"
    return here or "-"


def updatable(plugin: Plugin) -> bool:
    """Whether Update makes sense: the extras have another version than the one installed. Without a
    declared version there's no telling, so it's offered."""
    found = plugin.server or plugin.skill
    available, here = (found.version, found.installed_version) if found else ("", "")
    return plugin.installed and (not available or available != here)


def plugins(contents: RepositoryContents) -> list[Plugin]:
    return [Plugin(s.name, s.installed, server=s) for s in contents.servers] + [
        Plugin(s.name, s.installed, skill=s) for s in contents.skills
    ]


def label(plugin: Plugin) -> str:
    return f"{plugin.name} {version(plugin)}  {'✓ installed' if plugin.installed else '· not installed'}"


def matches(plugin: Plugin, query: str) -> bool:
    """By name, description or kind."""
    return query.strip().lower() in f"{plugin.name} {plugin.description} {plugin.kind}".lower()


def describe(plugin: Plugin) -> str:
    """Markdown: what it is, what it asks for, and its state."""
    lines = [f"## {plugin.name}", plugin.description, f"Kind: {plugin.kind}", f"Version: {version(plugin)}"]
    if plugin.server is not None:
        lines.append(f"Runs: {'remotely' if plugin.server.transport == 'http' else "on the assistant's computer"}")
        if plugin.server.fields:
            lines.append(f"Asks for: {', '.join(f.label for f in plugin.server.fields)}")
        if plugin.server.page:
            lines.append("Its page shows in the sidebar of the web app.")
        if plugin.server.channel:
            lines.append("Once it's installed, set it up in /channels.")
    elif plugin.skill is not None and plugin.skill.files:
        lines.append(f"Files: {', '.join(plugin.skill.files)}")
    lines.append(f"State: {'installed' if plugin.installed else 'not installed'}")
    return "\n\n".join(line for line in lines if line)
