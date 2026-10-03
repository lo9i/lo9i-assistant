"""How plugins read in the terminal app: the list of what the extras offer, and one plugin's details."""

from dataclasses import dataclass

from assistant.core.agent import FoundServer, FoundSkill, RepositoryContents


@dataclass(frozen=True)
class Plugin:
    """A plugin the extras offer: an MCP server (maybe with its skill and a page) or a skill of its own."""

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
        """ "MCP server · skill · page", or "Skill"."""
        if self.server is None:
            return "Skill"
        return " · ".join(
            ["MCP server", *(["skill"] if self.server.skill else []), *(["page"] if self.server.page else [])]
        )


def plugins(contents: RepositoryContents) -> list[Plugin]:
    return [Plugin(s.name, s.installed, server=s) for s in contents.servers] + [
        Plugin(s.name, s.installed, skill=s) for s in contents.skills
    ]


def label(plugin: Plugin) -> str:
    return f"{plugin.name}  {'✓ installed' if plugin.installed else '· not installed'}"


def matches(plugin: Plugin, query: str) -> bool:
    """By name, description or kind."""
    return query.strip().lower() in f"{plugin.name} {plugin.description} {plugin.kind}".lower()


def describe(plugin: Plugin) -> str:
    """Markdown: what it is, what it asks for, and its state."""
    lines = [f"## {plugin.name}", plugin.description, f"Kind: {plugin.kind}"]
    if plugin.server is not None:
        lines.append(f"Runs: {'on this computer' if plugin.server.transport == 'stdio' else 'remotely'}")
        if plugin.server.fields:
            lines.append(f"Asks for: {', '.join(f.label for f in plugin.server.fields)}")
        if plugin.server.page:
            lines.append("Its page shows in the sidebar of the web app.")
    elif plugin.skill is not None and plugin.skill.files:
        lines.append(f"Files: {', '.join(plugin.skill.files)}")
    lines.append(f"State: {'installed' if plugin.installed else 'not installed'}")
    return "\n\n".join(line for line in lines if line)
