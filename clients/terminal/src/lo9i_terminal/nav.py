"""The terminal app's navigation, as the web app's sidebar has it (its lib/ui/Sidebar.svelte): Home, Chat with the
conversations open under it, the pages, and Settings, whose sections are grouped in tabs on its page as the web app's
are (screens/settings.py). Each page and section has a key the sidebar and the slash commands open it by; collapsed,
the sidebar shows each page by its glyph."""

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
    """A tab of Settings, as the web app's: its sections in columns, as the web app's cards are. One section alone fills
    the tab, framed as a card where the web app shows one (`card`) and not where it shows a page of its own (Plugins,
    Logs). A section's key is its slash command's name."""

    key: str
    label: str
    columns: tuple[tuple[str, ...], ...]
    card: bool = False

    @property
    def sections(self) -> tuple[str, ...]:
        """Its sections' keys, a column after the other."""
        return tuple(key for column in self.columns for key in column)


def _alone(key: str) -> tuple[tuple[str, ...], ...]:
    return ((key,),)


# Settings' tabs, with the web app's order and labels (its lib/ui/settings/SettingsTabs.svelte) and its cards' columns
# (routes/settings/+page.svelte, routes/skills): General's balanced as the web app's are, since its own first column's
# cards (the assistant, the agent notices, the folder panel) are elsewhere here or the browser's, and Audio without
# the cards of what only a browser does (live voice calls, the microphone).
SETTINGS_TABS: tuple[SettingsTab, ...] = (
    SettingsTab("general", translatable("General"), (("language", "briefing"), ("startup", "websearch", "email"))),
    SettingsTab("memory", translatable("About you"), _alone("profile")),
    SettingsTab("model", translatable("Model"), (("model",), ("limits",))),
    SettingsTab("prompt", translatable("System prompt"), _alone("prompt"), card=True),
    SettingsTab("audio", translatable("Audio"), (("audio",), ("spoken",))),
    SettingsTab("plugins", translatable("Plugins"), _alone("plugins")),
    SettingsTab("mcp", translatable("MCP servers"), _alone("mcp")),
    SettingsTab("skills", translatable("Skills"), (("skills", "import-skills"),)),
    SettingsTab("system", translatable("System"), (("host",), ("keys",))),
    SettingsTab("clients", translatable("Clients"), _alone("sessions"), card=True),
    SettingsTab("logs", translatable("Logs"), _alone("logs")),
    SettingsTab("doctor", translatable("Health"), _alone("doctor")),
)

# Every section's key, in the order the tabs show them.
SETTINGS_SECTIONS: tuple[str, ...] = tuple(key for tab in SETTINGS_TABS for key in tab.sections)


def settings_tab(section: str) -> SettingsTab:
    """The tab a section shows in."""
    return next(tab for tab in SETTINGS_TABS if section in tab.sections)


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
