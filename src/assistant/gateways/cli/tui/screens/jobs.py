"""Scheduled jobs: pick one to see its task and recent runs, pause or resume it, or delete it.
Refreshes when a job runs or changes."""

from collections.abc import Awaitable, Callable
from typing import ClassVar

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Markdown, OptionList, Static
from textual.widgets.option_list import Option

from assistant.client.daemon_client import JobsApi
from assistant.core.agent import Job, JobError
from assistant.gateways.cli.jobs_text import describe, summary
from assistant.gateways.cli.tui.daemon_errors import reports_daemon_unavailable


class JobsScreen(ModalScreen[None]):
    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "dismiss", "Close")]

    def __init__(self, jobs: JobsApi) -> None:
        super().__init__()
        self._jobs = jobs
        self._shown: dict[str, Job] = {}
        self._selected: str | None = None

    def compose(self) -> ComposeResult:
        with Vertical(id="jobs"):
            yield Static("Scheduled jobs", id="jobs-title")
            yield Static(
                "No scheduled jobs. Ask the assistant for one, for example: “every day at 9 send me a news digest”.",
                id="jobs-empty",
            )
            with Horizontal(id="jobs-main"):
                yield OptionList(id="jobs-list")
                with VerticalScroll(id="jobs-detail"):
                    yield Markdown(id="job-body")
            with Horizontal(id="jobs-buttons"):
                yield Button("Pause", id="toggle")
                yield Button("Delete", variant="error", id="delete")
                yield Button("Close", id="close")

    @reports_daemon_unavailable
    async def on_mount(self) -> None:
        await self.reload()

    @reports_daemon_unavailable
    async def reload(self) -> None:
        """Called when a job runs or changes."""
        jobs = await self._jobs.list()
        self._shown = {j.name: j for j in jobs}
        options = self.query_one("#jobs-list", OptionList)
        options.clear_options()
        options.add_options([Option(f"{j.name}\n  {summary(j).replace('`', '')}", id=j.name) for j in jobs])
        # Empty: just the message, and the dialog shrinks to fit.
        self.query_one("#jobs").set_class(not jobs, "empty")
        self.query_one("#toggle").display = self.query_one("#delete").display = bool(jobs)
        if not jobs:
            self._selected = None
            self.query_one("#close", Button).focus()
            return
        keep = self._selected if self._selected in self._shown else jobs[0].name
        options.highlighted = list(self._shown).index(keep)
        await self._show(keep)

    @reports_daemon_unavailable
    async def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        if event.option.id is not None:
            await self._show(event.option.id)

    @on(Button.Pressed, "#close")
    def _close(self) -> None:
        self.dismiss()

    @on(Button.Pressed, "#toggle")
    @reports_daemon_unavailable
    async def _toggle(self) -> None:
        job = self._shown.get(self._selected or "")
        if job is not None:
            await self._change(lambda: self._jobs.set_enabled(job.name, not job.enabled))

    @on(Button.Pressed, "#delete")
    @reports_daemon_unavailable
    async def _delete(self) -> None:
        name = self._selected
        if name is not None and await self._change(lambda: self._jobs.delete(name)):
            self.notify(f"Deleted job {name}.")

    async def _change(self, action: Callable[[], Awaitable[object]]) -> bool:
        """Runs a change and shows the result. False (with the reason shown) when it wasn't possible."""
        try:
            await action()
        except JobError as e:
            self.notify(str(e), severity="error")
            return False
        finally:
            await self.reload()
        return True

    async def _show(self, name: str) -> None:
        self._selected = name
        job = self._shown[name]
        self.query_one("#toggle", Button).label = "Pause" if job.enabled else "Resume"
        await self.query_one("#job-body", Markdown).update(describe(job))
