"""Chat widgets for the Textual app."""

import json
import time
from collections.abc import Awaitable, Callable
from typing import Any

from rich.markup import escape
from textual import work
from textual.containers import VerticalScroll
from textual.widgets import Collapsible, Markdown, Static

from assistant.client.errors import DaemonUnavailableError
from assistant.core.agent import ConversationError, ConversationStats, MemorySnapshot, ShownCall
from assistant_terminal.context_text import detail, fuel
from assistant_terminal.i18n import t, translatable
from assistant_terminal.profile_text import section_label

_FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"


# Said after a message the user sent a handed-off agent while it worked (UserSaid.waiting), until it takes it.
WAITING = translatable("waiting for the agent to get to it")
# The run ended before the agent got to it: it went to the agent as the next message.
UNTAKEN = translatable("not taken: sent again below")
# The messages it hadn't taken, as that next message (core/conversation/resent.py).
RESENT = translatable("sent again")


class UserMessage(Static):
    """What the user wrote; `note`, dimmed under it, says where a message to a handed-off agent is (WAITING, ...)."""

    def __init__(self, text: str, attachments: list[str], note: str = "") -> None:
        self._lines = [f"> {escape(text)}", *(f"  📎 {escape(name)}" for name in attachments)]
        super().__init__(self._shown(note))

    def note(self, note: str) -> None:
        """Shows `note`, a translatable text, under it instead; none for ""."""
        self.update(self._shown(note))

    def _shown(self, note: str) -> str:
        return "\n".join([*self._lines, *([f"[dim]  {escape(t(note))}[/dim]"] if note else [])])


class TranscriptNote(Static):
    def __init__(self, text: str, language: str) -> None:
        super().__init__(t("🎤 heard ({language}): {text}", language=language, text=escape(text or t("(no speech)"))))


class ThinkingNote(Collapsible):
    """A handed-off agent's thinking: collapsed, its first line; expanded, the whole of it under
    "Thinking", so the first line isn't shown twice. It streams (`add`)."""

    _PREVIEW = 100

    def __init__(self, text: str) -> None:
        self._text = text
        self._body = Static(text, classes="thinking-text", markup=False)
        super().__init__(self._body, title=self._heading(collapsed=True), collapsed=True)

    def add(self, text: str) -> None:
        self._text += text
        self._body.update(self._text)
        self.title = self._heading(self.collapsed)

    def watch_collapsed(self, collapsed: bool) -> None:
        """Called after Collapsible's own watcher, which shows or hides the body."""
        self.title = self._heading(collapsed)

    def _heading(self, collapsed: bool) -> str:
        if not collapsed:
            return "✻ " + t("Thinking")
        first = self._text.strip().splitlines()[0] if self._text.strip() else ""
        return f"✻ {first if len(first) <= self._PREVIEW else first[: self._PREVIEW] + '…'}"


class CarriedNote(Collapsible):
    """A quick exchange the inbox carried to this conversation, before the message that followed it up:
    collapsed under "From the inbox"."""

    def __init__(self, text: str) -> None:
        super().__init__(Markdown(text, classes="carried-text"), title="↳ " + t("From the inbox"), collapsed=True)


class BriefNote(Collapsible):
    """A coding task the assistant wrote for the agent it handed the conversation to: not the user's message, so
    collapsed under "Task for <agent>" instead of shown as theirs."""

    def __init__(self, text: str, agent: str) -> None:
        super().__init__(
            Markdown(text, classes="brief-text"), title="↳ " + t("Task for {agent}", agent=agent), collapsed=True
        )


class FollowUpNote(Static):
    """Background work that ended, which the assistant followed up on without a message from the user."""

    def __init__(self, notice: str) -> None:
        super().__init__(f"↳ {escape(notice)}", classes="follow-up-note")


class HeldNote(Static):
    """An update installs: what the user sent is kept, and runs once lo9i is back, announced with `held_id`."""

    def __init__(self, held_id: str) -> None:
        super().__init__(
            "⏳ " + escape(t("An update is being installed. This runs once it's done.")), classes="follow-up-note"
        )
        self.held_id = held_id


class ToolNote(Static):
    """A tool the assistant used, in a conversation shown again after resuming it."""

    def __init__(self, name: str) -> None:
        super().__init__(f"✓ {escape(name)}")


class StoppedNote(Static):
    """The user stopped the reply (Esc)."""

    def __init__(self) -> None:
        super().__init__("■ " + t("Stopped."))


class AssistantMessage(Markdown):
    """A reply. Text is streamed into it with `Markdown.get_stream`."""


class SystemNote(Markdown):
    """Help and status text from the app itself, not from the assistant."""


class ErrorMessage(Static):
    def __init__(self, message: str) -> None:
        super().__init__("⏺ " + t("Error: {message}", message=escape(message)))


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
        steps = t("1 step") if self._steps == 1 else t("{count} steps", count=self._steps)
        self.title = f"⏺ {self._call} · {steps}"

    def finish(self, output: str) -> None:
        self._result.update(output.strip() or t("(no output)"))
        self.title = self.title.replace("⏺", "✓", 1)

    def cancel(self) -> None:
        self._result.update(t("(cancelled)"))
        self.title = self.title.replace("⏺", "✗", 1)


class PartialToolCall(ToolCall):
    """A tool call history shows the start of, or a step inside one: its arguments on one line and the start of its
    output. The whole call loads the first time it's expanded; one that couldn't load tries again the next time."""

    def __init__(self, name: str, args: dict[str, Any], output: str, load: Callable[[], Awaitable[ShownCall]]) -> None:
        super().__init__(name, args)
        self._name, self._preview, self._load, self._whole = name, output.strip(), load, False
        self.finish(output)

    def on_collapsible_expanded(self, event: Collapsible.Expanded) -> None:
        if event.collapsible is self and not self._whole:
            self._load_whole()

    @work(exclusive=True)
    async def _load_whole(self) -> None:
        self._result.update(self._noted(t("Loading the whole call…")))
        try:
            whole = await self._load()
        except (ConversationError, DaemonUnavailableError):
            self._result.update(self._noted(t("Couldn't load the whole call.")))
            return
        self._whole = True
        self._call = f"{self._name}({_describe(whole.args)})" if whole.args else self._name
        self.title = f"✓ {self._call}"
        self._result.update(whole.output.strip() or t("(no output)"))

    def _noted(self, note: str) -> str:
        return "\n\n".join(filter(None, [self._preview, note]))


class ContextFuel(Static):
    """How full the conversation's context is, in the footer (context_text.py); the figures on hover."""

    def show(self, stats: ConversationStats | None) -> None:
        self.update(fuel(stats) if stats else "")
        self.tooltip = detail(stats) if stats else None


class MouseStatus(Static):
    """Whether clicks work now, at the end of the footer, and what the next start brings when a
    change couldn't be applied yet."""

    def __init__(self, active: bool) -> None:
        super().__init__()
        self.active = active
        self.show(active)

    def show(self, active: bool, pending: bool | None = None) -> None:
        self.active = active
        after = ""
        if pending is not None and pending != active:
            after = " " + (t("(on after restart)") if pending else t("(off after restart)"))
        self.update((t("mouse on") if active else t("mouse off")) + after)


class ConnectionNote(Static):
    """Says the assistant can't be reached while the app's event stream is lost (a restart, a computer that slept),
    as the web app's banner does, and that it's back."""

    def __init__(self) -> None:
        super().__init__(
            "⚠ " + t("Can't reach the assistant right now. It may be restarting. Reconnecting…"), id="connection"
        )
        self.display = False

    def lost(self) -> None:
        self.display = True

    def back(self) -> None:
        if self.display:
            self.display = False
            self.app.notify(t("Connected to the assistant again."))


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
    profile = [f"[b]{section_label(name)}[/b]: {escape('; '.join(items))}" for name, items in snapshot.profile.items()]
    sections = [
        (t("Profile"), profile),
        (t("Skills"), [f"• {escape(s)}" for s in snapshot.skills]),
    ]
    empty = "[dim]" + t("(empty)") + "[/]"
    return "\n\n".join(f"[b]{title}[/b]\n" + ("\n".join(lines) or empty) for title, lines in sections)


def _describe(args: dict[str, Any]) -> str:
    if len(args) == 1:
        return str(next(iter(args.values())))
    return json.dumps(args, ensure_ascii=False)
