"""Chat widgets for the Textual app."""

import json
import time
from typing import Any

from rich.markup import escape
from textual.containers import VerticalScroll
from textual.widgets import Collapsible, Markdown, Static

from assistant.core.agent import MemorySnapshot

_FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"


class UserMessage(Static):
    def __init__(self, text: str, attachments: list[str]) -> None:
        lines = [f"> {escape(text)}", *(f"  📎 {escape(name)}" for name in attachments)]
        super().__init__("\n".join(lines))


class TranscriptNote(Static):
    def __init__(self, text: str, language: str) -> None:
        super().__init__(f"🎤 heard ({language}): {escape(text or '(no speech)')}")


class ThinkingNote(Collapsible):
    """A handed-off agent's thinking: its first line, the rest when expanded."""

    _TITLE = 100

    def __init__(self, text: str) -> None:
        first = text.strip().splitlines()[0] if text.strip() else ""
        title = first if len(first) <= self._TITLE else first[: self._TITLE] + "…"
        super().__init__(Static(text, classes="thinking-text", markup=False), title=f"✻ {title}", collapsed=True)


class ToolNote(Static):
    """A tool the assistant used, in a conversation shown again after resuming it."""

    def __init__(self, name: str) -> None:
        super().__init__(f"✓ {escape(name)}")


class StoppedNote(Static):
    """The user stopped the reply (Esc)."""

    def __init__(self) -> None:
        super().__init__("■ Stopped.")


class AssistantMessage(Markdown):
    """A reply. Text is streamed into it with `Markdown.get_stream`."""


class SystemNote(Markdown):
    """Help and status text from the app itself, not from the assistant."""


class ErrorMessage(Static):
    def __init__(self, message: str) -> None:
        super().__init__(f"⏺ Error: {escape(message)}")


class ToolCall(Collapsible):
    """A tool call. The title shows the call; the collapsed body holds the result, after the calls
    of a delegate call's subagent."""

    def __init__(self, name: str, args: dict[str, Any]) -> None:
        # A step a handed-off agent reports is a line of text, with no arguments to show.
        self._call = f"{name}({_describe(args)})" if args else name
        self._steps = 0
        self._result = Static("…", classes="tool-result", markup=False)
        super().__init__(self._result, title=f"⏺ {self._call}", collapsed=True)

    async def add_step(self, step: "ToolCall") -> None:
        self._steps += 1
        await self.query_one(Collapsible.Contents).mount(step, before=self._result)
        self.title = f"⏺ {self._call} · {self._steps} {'step' if self._steps == 1 else 'steps'}"

    def finish(self, output: str) -> None:
        self._result.update(output.strip() or "(no output)")
        self.title = self.title.replace("⏺", "✓", 1)

    def cancel(self) -> None:
        self._result.update("(cancelled)")
        self.title = self.title.replace("⏺", "✗", 1)


class MouseStatus(Static):
    """Whether clicks work now, at the end of the footer, and what the next start brings when a
    change couldn't be applied yet."""

    def __init__(self, active: bool) -> None:
        super().__init__()
        self.active = active
        self.show(active)

    def show(self, active: bool, pending: bool | None = None) -> None:
        self.active = active
        after = f" ({_on_off(pending)} after restart)" if pending is not None and pending != active else ""
        self.update(f"mouse {_on_off(active)}{after}")


def _on_off(on: bool) -> str:
    return "on" if on else "off"


class StatusLine(Static):
    """'⠋ Thinking… 12s' while the agent works, empty otherwise."""

    def on_mount(self) -> None:
        self._label = ""
        self._hint = ""
        self._started = 0.0
        self._frame = 0
        self.set_interval(0.1, self._tick)

    def show(self, label: str, hint: str = "") -> None:
        """`hint` names a key that acts on what's shown, such as Esc to stop."""
        self._hint = hint
        if label != self._label:
            self._label = label
            self._started = time.monotonic()

    def clear(self) -> None:
        self._label = ""
        self.update("")

    def _tick(self) -> None:
        if not self._label:
            return
        self._frame += 1
        elapsed = int(time.monotonic() - self._started)
        hint = f"  ({self._hint})" if self._hint else ""
        self.update(f"{_FRAMES[self._frame % len(_FRAMES)]} {self._label}… {elapsed}s{hint}")


class MemoryPanel(VerticalScroll):
    """Read-only view of the profile and skills."""

    def compose(self):
        yield Static(id="memory-body")

    def show(self, snapshot: MemorySnapshot) -> None:
        self.query_one("#memory-body", Static).update(_render_snapshot(snapshot))


def _render_snapshot(snapshot: MemorySnapshot) -> str:
    profile = [
        f"[b]{name.replace('_', ' ').capitalize()}[/b]: {escape('; '.join(items))}"
        for name, items in snapshot.profile.items()
    ]
    sections = [
        ("Profile", profile),
        ("Skills", [f"• {escape(s)}" for s in snapshot.skills]),
    ]
    return "\n\n".join(f"[b]{title}[/b]\n" + ("\n".join(lines) or "[dim](empty)[/]") for title, lines in sections)


def _describe(args: dict[str, Any]) -> str:
    if len(args) == 1:
        return str(next(iter(args.values())))
    return json.dumps(args, ensure_ascii=False)
