"""The terminal app's navigation, as the web app's sidebar has it (its lib/ui/Sidebar.svelte): Home, Chat with the
conversations open under it, the pages, and Settings, whose sections are tabs on its page (screens/settings.py).
Each page and section has a key the sidebar and the slash commands open it by; collapsed, the sidebar shows each page
by its glyph."""

from collections.abc import Mapping
from dataclasses import dataclass, field

from rich.text import Text

from lo9i_terminal.i18n import t, translatable
from lo9i_terminal.open_text import OpenItem

CHAT = "chat"
SETTINGS = "settings"
# An open conversation's entry: this prefix and its thread id.
OPEN = "open:"


@dataclass(frozen=True)
class Page:
    key: str
    label: str
    # One cell wide, for the collapsed sidebar.
    glyph: str


PAGES: tuple[Page, ...] = (
    Page("home", translatable("Home"), "⌂"),
    Page(CHAT, translatable("Chat"), "✎"),
    Page("conversations", translatable("Conversations"), "≡"),
    Page("subagents", translatable("Subagents"), "◈"),
    Page("files", translatable("Files"), "▤"),
    Page("usage", translatable("Usage"), "▥"),
    Page("jobs", translatable("Jobs"), "◷"),
    Page("devices", translatable("Devices"), "▣"),
    Page("notifications", translatable("Notifications"), "✉"),
    Page("alerts", translatable("Alerts"), "!"),
    Page(SETTINGS, translatable("Settings"), "✱"),
)


@dataclass(frozen=True)
class SettingsTab:
    """A section of Settings: its key is its slash command's name."""

    key: str
    label: str


# Settings' sections, one tab each, in the web app's order: its General tab's cards first, then its other tabs.
SETTINGS_TABS: tuple[SettingsTab, ...] = (
    SettingsTab("language", translatable("Language")),
    SettingsTab("briefing", translatable("Briefing and reviews")),
    SettingsTab("websearch", translatable("Web search")),
    SettingsTab("email", translatable("Email")),
    SettingsTab("startup", translatable("Start at boot")),
    SettingsTab("profile", translatable("About you")),
    SettingsTab("model", translatable("Model")),
    SettingsTab("limits", translatable("Spending limits")),
    SettingsTab("prompt", translatable("System prompt")),
    SettingsTab("audio", translatable("Audio")),
    SettingsTab("plugins", translatable("Plugins")),
    SettingsTab("mcp", translatable("MCP servers")),
    SettingsTab("skills", translatable("Skills")),
    SettingsTab("host", translatable("System")),
    SettingsTab("keys", translatable("Kept keys")),
    SettingsTab("sessions", translatable("Clients")),
    SettingsTab("logs", translatable("Logs")),
    SettingsTab("doctor", translatable("Health")),
)


@dataclass(frozen=True)
class NavState:
    """What the sidebar shows besides its pages: the conversations open, and a count beside a page (those waiting for
    an answer beside Chat, the subagents working, the notifications unread, what needs
    attention beside Alerts, the plugin updates beside Settings)."""

    open: tuple[OpenItem, ...] = ()
    counts: Mapping[str, int] = field(default_factory=dict)


def entries(page: str, state: NavState, collapsed: bool) -> list[tuple[str, Text]]:
    """The sidebar's lines on `page`, each with its id: a page's (its key), an open conversation's (`OPEN` and its
    thread id); collapsed, only the pages' glyphs."""
    lines: list[tuple[str, Text]] = []
    for item in PAGES:
        line = _page_line(item, state.counts.get(item.key, 0), collapsed)
        lines.append((item.key, _here(line) if item.key == page else line))
        if item.key == CHAT and not collapsed:
            lines += [(OPEN + o.thread_id, _open_line(o)) for o in state.open]
    return lines


def _here(line: Text) -> Text:
    """The page shown, wherever the sidebar's highlight is."""
    line.stylize("bold underline")
    return line


def _page_line(page: Page, count: int, collapsed: bool) -> Text:
    if collapsed:
        return Text(page.glyph + ("•" if count else " "))
    line = Text(f"{page.glyph} {t(page.label)}")
    if count:
        line.append(f"  {count}", style="bold")
    return line


def _open_line(item: OpenItem) -> Text:
    """As herdr marks its agents: ◉ waiting for you, ● working, ○ neither; the one shown in bold."""
    marker = "◉" if item.waiting else "●" if item.running else "○"
    return Text(f"  {marker} {item.title}", style="bold" if item.current else "")
