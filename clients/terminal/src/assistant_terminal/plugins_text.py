"""How plugins read in the terminal app: the list of what the repositories offer (the official extras
and the ones the user added), and one plugin's details."""

from dataclasses import dataclass
from datetime import UTC, datetime

from assistant.core.agent import FoundServer, FoundSkill, Repository, RepositoryContents, RepositoryPlugins
from assistant.core.repositories.known import EXTRAS
from assistant_terminal.i18n import t, translatable

_EXTRAS = Repository(EXTRAS, "lo9i/lo9i-assistant-extras", True)


@dataclass(frozen=True)
class Plugin:
    """A plugin a repository offers: an MCP server (maybe with its skill, a page or a chat channel), a
    chat channel, or a skill of its own."""

    name: str
    installed: bool
    server: FoundServer | None = None
    skill: FoundSkill | None = None
    repository: Repository = _EXTRAS

    @property
    def key(self) -> str:
        # A server and a skill can share a name, and two repositories a plugin's name.
        return f"{self.repository.url}|{'server' if self.server else 'skill'}:{self.name}"

    @property
    def description(self) -> str:
        return self.server.description if self.server else self.skill.description if self.skill else ""

    @property
    def category(self) -> str:
        """What it's for, from the daemon's fixed list: a group and a category in it ("communications/email")."""
        return self.server.category if self.server else self.skill.category if self.skill else "other/general"

    @property
    def group(self) -> str:
        """The group its category is in: "communications/email" → "communications"."""
        return self.category.split("/")[0]

    @property
    def kind(self) -> str:
        """ "MCP server · channel · skill · page", "Channel" (a chat channel without tools), "Email
        provider", "Coding agent · skill", or "Skill"."""
        if self.server is None:
            return t("Skill")
        parts = [
            (t("MCP server"), self.server.transport != "none"),
            (t("channel"), self.server.channel),
            (t("email provider"), self.server.email),
            (t("coding agent"), bool(self.server.agent)),
            (t("skill"), self.server.skill),
            (t("page"), self.server.page),
        ]
        kind = " · ".join(part for part, has in parts if has)
        return kind[:1].upper() + kind[1:]


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


def has_newer(plugin: Plugin) -> bool:
    """The extras have a newer version than the one installed: both declare one and they differ."""
    found = plugin.server or plugin.skill
    return plugin.installed and found is not None and bool(found.version) and found.version != found.installed_version


def update_label(plugin: Plugin) -> str:
    """ "expenses  0.2.2 → 0.3.0", for the list of updates."""
    found = plugin.server or plugin.skill
    none = t("none")
    installed, available = (found.installed_version or none, found.version) if found else (none, "")
    return f"{plugin.name}  {installed} → {available}"


def plugins(contents: RepositoryContents, repository: Repository = _EXTRAS) -> list[Plugin]:
    return [Plugin(s.name, s.installed, server=s, repository=repository) for s in contents.servers] + [
        Plugin(s.name, s.installed, skill=s, repository=repository) for s in contents.skills
    ]


def from_repositories(read: list[RepositoryPlugins]) -> tuple[list[Plugin], list[str]]:
    """Every repository's plugins, the official extras first, and what the ones that couldn't be read
    said, or the plugins in them that couldn't be."""
    found = [p for r in read if r.contents for p in plugins(r.contents, r.repository)]
    errors = [f"{r.repository.name}: {r.error}" for r in read if r.error]
    problems = [f"{r.repository.name}: {p}" for r in read if r.contents for p in r.contents.problems]
    return found, [*errors, *problems]


def last_checked(read: list[RepositoryPlugins]) -> str:
    """When every repository was last checked: the oldest of their checks, "" while one never was (as the web
    app's lib/plugins.ts says it)."""
    times = [r.contents.checked if r.contents else "" for r in read]
    return "" if not times or "" in times else min(times)


def checked_line(checked: str, checking: bool, failed: bool, now: datetime) -> str:
    """Beside the list, which is the one kept from the last check while the repositories are checked again."""
    if checking:
        return t("Checking for updates…")
    when = t("checked {ago}", ago=_ago(datetime.fromisoformat(checked), now)) if checked else ""
    if failed:
        return t("Couldn't check for updates") + (f" · {when}" if when else "")
    return when[:1].upper() + when[1:]


_UNITS = (
    (24 * 60, translatable("{count} day ago"), translatable("{count} days ago")),
    (60, translatable("{count} hour ago"), translatable("{count} hours ago")),
    (1, translatable("{count} minute ago"), translatable("{count} minutes ago")),
)


def _ago(then: datetime, now: datetime) -> str:
    minutes = int((now - (then if then.tzinfo else then.replace(tzinfo=UTC))).total_seconds() // 60)
    for size, one, many in _UNITS:
        if minutes >= size:
            count = minutes // size
            return t(many if count > 1 else one, count=count)
    return t("just now")


def source(plugin: Plugin) -> str:
    """ "Official" for the extras' plugins; the repository's name for the others."""
    return t("Official") if plugin.repository.official else t("{name} (not official)", name=plugin.repository.name)


def by_category(shown: list[Plugin]) -> list[tuple[str, list[Plugin]]]:
    """The plugins grouped by their category's group, in alphabetical order with "other" last, keeping
    their order within a group."""
    groups = sorted({p.group for p in shown}, key=lambda g: (g == "other", g))
    return [(g, [p for p in shown if p.group == g]) for g in groups]


def category_label(category: str) -> str:
    """ "communications/email" → "Communications / Email"; a group alone, "communications" → "Communications"."""
    return " / ".join(
        t(_CATEGORY_PARTS[part]) if part in _CATEGORY_PARTS else part.capitalize() for part in category.split("/")
    )


# The parts of the daemon's fixed list of categories (core/repositories/categories.py).
_CATEGORY_PARTS = {
    "agents": translatable("Agents"),
    "apps": translatable("Apps"),
    "assistant": translatable("Assistant"),
    "calendar": translatable("Calendar"),
    "chat": translatable("Chat"),
    "communications": translatable("Communications"),
    "connectivity": translatable("Connectivity"),
    "contacts": translatable("Contacts"),
    "email": translatable("Email"),
    "factory": translatable("Factory"),
    "finance": translatable("Finance"),
    "general": translatable("General"),
    "maps": translatable("Maps"),
    "media": translatable("Media"),
    "modes": translatable("Modes"),
    "news": translatable("News"),
    "other": translatable("Other"),
    "phone": translatable("Phone"),
    "productivity": translatable("Productivity"),
    "remote": translatable("Remote"),
    "software": translatable("Software"),
    "video": translatable("Video"),
}


def label(plugin: Plugin) -> str:
    """Its row in the list: the name, and the repository it's from when that isn't the official
    extras. Its version and state are in its details beside it."""
    return plugin.name if plugin.repository.official else f"{plugin.name}  [dim]{plugin.repository.name}[/dim]"


def matches(plugin: Plugin, query: str) -> bool:
    """By name, description, kind, category or repository."""
    text = f"{plugin.name} {plugin.description} {plugin.kind} {plugin.category} {plugin.repository.name}"
    return query.strip().lower() in text.lower()


def describe(plugin: Plugin) -> str:
    """Markdown: what it is, what it asks for, and its state."""
    lines = [
        f"## {plugin.name}",
        plugin.description,
        t("Source: {source}", source=source(plugin)),
        t("Category: {category}", category=category_label(plugin.category)),
        t("Kind: {kind}", kind=plugin.kind),
        t("Version: {version}", version=version(plugin)),
    ]
    if plugin.server is not None:
        remote = plugin.server.transport == "http"
        lines.append(t("Runs: remotely") if remote else t("Runs: on the assistant's computer"))
        if plugin.server.fields:
            lines.append(t("Asks for: {fields}", fields=", ".join(f.label for f in plugin.server.fields)))
        if plugin.server.page:
            lines.append(t("Its page shows in the sidebar of the web app."))
        if plugin.server.channel:
            lines.append(t("Once it's installed, its setup shows here."))
        if plugin.server.email:
            lines.append(t("Once it's installed, connect its accounts with Accounts."))
    elif plugin.skill is not None and plugin.skill.files:
        lines.append(t("Files: {files}", files=", ".join(plugin.skill.files)))
    lines.append(t("State: installed") if plugin.installed else t("State: not installed"))
    return "\n\n".join(line for line in lines if line)
