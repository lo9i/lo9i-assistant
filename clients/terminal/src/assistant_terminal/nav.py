"""The terminal app's navigation, as the web app's sidebar has it (its lib/ui/Sidebar.svelte): Home, Chat with the
conversations open under it, the pages, and Settings, which opens into its sections as the web app's Settings tabs do.
Each page has a key the sidebar and the slash commands open it by; collapsed, the sidebar shows each by its glyph."""

from collections.abc import Mapping
from dataclasses import dataclass, field

from rich.text import Text

from assistant_terminal.i18n import t, translatable
from assistant_terminal.open_text import OpenItem

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
    Page("briefing", translatable("Briefing"), "☼"),
    Page("subagents", translatable("Subagents"), "◈"),
    Page("files", translatable("Files"), "▤"),
    Page("usage", translatable("Usage"), "▥"),
    Page("jobs", translatable("Jobs"), "◷"),
    Page("devices", translatable("Devices"), "▣"),
    Page("notifications", translatable("Notifications"), "✉"),
    Page(SETTINGS, translatable("Settings"), "✱"),
)

# Settings' sections, in the web app's order: its General tab's cards first, then its other tabs.
SETTINGS_PAGES: tuple[Page, ...] = (
    Page("language", translatable("Language"), "·"),
    Page("websearch", translatable("Web search"), "·"),
    Page("email", translatable("Email"), "·"),
    Page("startup", translatable("Start at boot"), "·"),
    Page("profile", translatable("About you"), "·"),
    Page("model", translatable("Model"), "·"),
    Page("limits", translatable("Spending limits"), "·"),
    Page("prompt", translatable("System prompt"), "·"),
    Page("audio", translatable("Audio"), "·"),
    Page("plugins", translatable("Plugins"), "·"),
    Page("mcp", translatable("MCP servers"), "·"),
    Page("skills", translatable("Skills"), "·"),
    Page("host", translatable("System"), "·"),
    Page("keys", translatable("Kept keys"), "·"),
    Page("sessions", translatable("Clients"), "·"),
    Page("logs", translatable("Logs"), "·"),
    Page("doctor", translatable("Health"), "·"),
)

_SETTINGS_KEYS = frozenset(p.key for p in SETTINGS_PAGES)


@dataclass(frozen=True)
class NavState:
    """What the sidebar shows besides its pages: the conversations open, and a count beside a page (those waiting for
    an answer beside Chat, the open loops beside Briefing, the subagents working, the notifications unread, the plugin
    updates beside Settings)."""

    open: tuple[OpenItem, ...] = ()
    counts: Mapping[str, int] = field(default_factory=dict)


def in_settings(page: str) -> bool:
    return page == SETTINGS or page in _SETTINGS_KEYS


def first_settings_page() -> str:
    return SETTINGS_PAGES[0].key


def entries(page: str, state: NavState, collapsed: bool) -> list[tuple[str, Text]]:
    """The sidebar's lines on `page`, each with its id: a page's (its key), an open conversation's (`OPEN` and its
    thread id). Settings' sections show while one of them is open; collapsed, only the pages' glyphs."""
    lines: list[tuple[str, Text]] = []
    for item in PAGES:
        line = _page_line(item, state.counts.get(item.key, 0), collapsed)
        lines.append((item.key, _here(line) if item.key == page else line))
        if collapsed:
            continue
        if item.key == CHAT:
            lines += [(OPEN + o.thread_id, _open_line(o)) for o in state.open]
        if item.key == SETTINGS and in_settings(page):
            lines += [(s.key, _settings_line(s, page)) for s in SETTINGS_PAGES]
    return lines


def _here(line: Text) -> Text:
    """The page shown, wherever the sidebar's highlight is."""
    line.stylize("bold underline")
    return line


def _settings_line(section: Page, page: str) -> Text:
    line = Text(f"   {t(section.label)}")
    return _here(line) if section.key == page else line


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
