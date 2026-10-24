"""Scheduled jobs: pick one to see its task and recent runs, read its last run's whole reply (a run's record
keeps only the end of it), pause or resume it, or delete it. A job run's notification opens it on that run's
reply. Refreshes when a job runs or changes."""

from collections.abc import Awaitable, Callable
from typing import ClassVar

from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Markdown, OptionList, Static
from textual.widgets.option_list import Option

from assistant.client.daemon_client import JobsApi
from assistant.core.agent import Job, JobError
from assistant_terminal.jobs_text import describe, with_reply
from assistant_terminal.tui.daemon_errors import reports_daemon_unavailable
from assistant_terminal.tui.screens.confirm import ConfirmScreen


class JobsScreen(ModalScreen[None]):
    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "dismiss", "Close")]

    def __init__(self, jobs: JobsApi, job: str | None = None, run: str | None = None) -> None:
        super().__init__()
        self._jobs = jobs
        self._shown: dict[str, Job] = {}
        self._selected = job
        # The run whose whole reply shows, by when it started.
        self._run = run

    def compose(self) -> ComposeResult:
        with Vertical(id="jobs"):
            yield Static("Scheduled jobs", id="jobs-title")
            yield Static(
                "No scheduled jobs. Ask the assistant for one, for example: “every day at 9 send me a news digest”.",
                id="jobs-empty",
            )
            with Horizontal(id="jobs-main"):
                yield OptionList(id="jobs-list")
                yield Static(classes="divider")
                with VerticalScroll(id="jobs-detail"):
                    yield Markdown(id="job-body")
            with Horizontal(id="jobs-buttons"):
                yield Button("Last reply", id="reply")
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
        # Only names; when it runs and the rest are in the detail next to the list.
        options.add_options([Option(j.name, id=j.name) for j in jobs])
        # Empty: just the message, and the dialog shrinks to fit.
        self.query_one("#jobs").set_class(not jobs, "empty")
        for button in ("#reply", "#toggle", "#delete"):
            self.query_one(button).display = bool(jobs)
        if not jobs:
            self._selected = None
            self.query_one("#close", Button).focus()
            return
        keep = self._selected if self._selected in self._shown else jobs[0].name
        options.highlighted = list(self._shown).index(keep)
        await self._show(keep)

    @reports_daemon_unavailable
    async def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        if event.option.id is not None and event.option.id != self._selected:
            self._run = None
            await self._show(event.option.id)

    @on(Button.Pressed, "#reply")
    @reports_daemon_unavailable
    async def _last_reply(self) -> None:
        job = self._shown.get(self._selected or "")
        if job is not None and job.runs:
            self._run = job.runs[-1].at
            await self._show(job.name)

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
    def _delete(self) -> None:
        if self._selected is not None:
            self._confirm_delete(self._selected)

    @work
    @reports_daemon_unavailable
    async def _confirm_delete(self, name: str) -> None:
        if not await self.app.push_screen_wait(ConfirmScreen(f"Delete the job {name}?", "Delete")):
            return
        if await self._change(lambda: self._jobs.delete(name)):
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
        self.query_one("#reply", Button).disabled = not job.runs
        await self.query_one("#job-body", Markdown).update(await self._text(job))

    async def _text(self, job: Job) -> str:
        """Its description, with the whole reply of the run opened, when it's still among its runs."""
        if self._run is None or not any(r.at == self._run for r in job.runs):
            return describe(job)
        try:
            return with_reply(job, self._run, await self._jobs.run_reply(job.name, self._run))
        except JobError as e:
            self.notify(str(e), severity="error")
            return describe(job)
