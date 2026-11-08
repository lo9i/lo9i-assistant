"""What a new conversation's context is made of, the system prompt part by part and the tool definitions, largest
first, each with a bar of its size, its tokens and its share of the model's window; as Settings → Context's card of
the same name in the web app, which draws them as a ring. Measured again when what it's made of changes."""

from typing import ClassVar

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Markdown, Static

from lo9i.client.daemon_client import DoctorApi
from lo9i.core.agent import StartingContext
from lo9i_terminal.context_text import compact
from lo9i_terminal.i18n import language, t
from lo9i_terminal.tui.daemon_errors import reports_daemon_unavailable
from lo9i_terminal.tui.section import SettingsSection
from lo9i_terminal.tui.theme import ACCENT, LINE, MUTED

_BAR = 16
# Below this a share shows as <0.01%, which says it's there without a row of zeros.
_TINY = 0.0001


def summary(context: StartingContext) -> str:
    total = t("{tokens} tokens, estimated at about 4 characters each.", tokens=compact(context.tokens))
    if not context.window:
        return total
    window = t(
        "Context window: {window} tokens, {used} used ({share}).",
        window=compact(context.window),
        used=compact(context.tokens),
        share=percent(context.tokens / context.window),
    )
    return f"{total} {window} " + t("Each part's share is of the window.")


def parts(context: StartingContext) -> Text:
    """A line a part, largest first: its bar against the largest, its name, tokens and share of the model's window (of
    the total while the window isn't known)."""
    shown = sorted((p for p in context.parts if p.tokens), key=lambda p: p.tokens, reverse=True)
    if not shown:
        return Text()
    largest, whole = shown[0].tokens, context.window or sum(p.tokens for p in shown)
    width = max(len(p.name) for p in shown)
    lines = Text()
    for part in shown:
        filled = max(1, round(_BAR * part.tokens / largest))
        lines.append("━" * filled, style=ACCENT).append("━" * (_BAR - filled), style=LINE)
        lines.append(f"  {part.name.ljust(width)}  {compact(part.tokens):>6}")
        lines.append(f"  {percent(part.tokens / whole):>6}\n", style=MUTED)
    lines.rstrip()
    return lines


def percent(share: float) -> str:
    """Like 42%, 0.4% or 0.04%: as many decimals as a small share needs to show."""
    if 0 < share < _TINY:
        return f"<{_decimal_percent(_TINY * 100, 2)}%"
    places = 2 if share < 0.001 else 1 if share < 0.01 else 0
    return f"{_decimal_percent(share * 100, places)}%"


def _decimal_percent(value: float, places: int) -> str:
    written = f"{value:.{places}f}"
    return written.replace(".", ",") if language() == "es" else written


class ContextPartsSection(SettingsSection):
    RELOADS_ON: ClassVar[frozenset[str]] = frozenset(
        {"memory", "skills", "mcp", "plugins", "integrations", "prompts", "settings"}
    )

    def __init__(self, doctor: DoctorApi) -> None:
        super().__init__()
        self._doctor = doctor

    def compose(self) -> ComposeResult:
        with Vertical(id="context-parts"):
            yield Markdown("## " + t("What the context is made of") + "\n\n" + t("Loading…"), id="context-parts-body")
            yield Static(id="context-parts-bars")
            with Horizontal(id="context-parts-buttons"):
                yield Button(t("Close"), id="close")

    @reports_daemon_unavailable
    async def on_mount(self) -> None:
        await self.reload()

    @reports_daemon_unavailable
    async def reload(self) -> None:
        context = await self._doctor.context()
        about = t(
            "What every new conversation sends the model before its first message: the system prompt part by part, "
            "then the tool definitions. Facts that aren't basic and summaries of past conversations aren't in it: they "
            "come into a turn when a message touches them."
        )
        heading = "## " + t("What the context is made of")
        await self.query_one("#context-parts-body", Markdown).update(f"{heading}\n\n{about} {summary(context)}")
        self.query_one("#context-parts-bars", Static).update(parts(context))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "close":
            self.close()
