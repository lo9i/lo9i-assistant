"""Background subagents: tasks the assistant sends off with `delegate(..., background=True)` (core/tools/delegate.py)
to work while the conversation goes on. Several run at once, with no step limit; the delegate call returns at once,
and each one's answer goes back to the conversation that sent it off when it ends (ends.py). An approval one needs
pauses only it: the apps show it on its card and answer it (`answer`), and a chat channel its conversation is on gets
it with buttons (core/approvals.py). The user can stop one.

The daemon runs this as a supervised task: it works on every one that hasn't ended, at start (from where its
checkpoints left it, so a restart loses at most the step in progress) and as they're sent off. When one ends, its
checkpoints and the files its tools brought go: its steps and answer are kept on its record, the latest `KEPT_ENDED`
of a conversation's, until the user removes them or the conversation is deleted."""

import asyncio
import contextlib
import logging
import uuid
from collections.abc import Callable, Collection
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

from langchain_core.messages import BaseMessage
from langchain_core.runnables import RunnableConfig

from lo9i.core import i18n, uploads
from lo9i.core.approvals import RemoteApprovals
from lo9i.core.attachments import upload_paths
from lo9i.core.background import BackgroundEnds, Origin, short
from lo9i.core.background_subagents import ends, records
from lo9i.core.background_subagents.records import (
    DONE,
    FAILED,
    STOPPED,
    BackgroundStep,
    BackgroundSubagent,
    Status,
)
from lo9i.core.background_subagents.work import SubagentWork, publish, thread
from lo9i.core.bus import EventBus
from lo9i.core.context import BackgroundSubagentStarts, Context
from lo9i.core.conversation import ended
from lo9i.core.events import ApprovalRequired
from lo9i.core.health import HealthLog
from lo9i.core.i18n import said
from lo9i.core.storage import Storage
from lo9i.core.subagent import SubagentRunner
from lo9i.core.waiting import first

logger = logging.getLogger(__name__)

# The ended ones a conversation keeps, the newest.
KEPT_ENDED = 20
_ASKED_TITLE = 60


class SubagentError(Exception):
    """The subagent can't do that now; the text says why."""


class SubagentNotFoundError(SubagentError):
    """No such subagent."""


class BackgroundSubagents(BackgroundSubagentStarts):
    name = "background subagents"

    def __init__(
        self,
        storage: Storage,
        bus: EventBus,
        health: HealthLog,
        approvals: RemoteApprovals,
        ends: BackgroundEnds,
        runner: Callable[[], SubagentRunner],
        context: Callable[[str, str], Context],
    ) -> None:
        """`runner`: the subagents of the model in use; `context`: a run's context for a user and channel."""
        self._storage = storage
        self._bus = bus
        self._health = health
        self._approvals = approvals
        self._ends = ends
        self._runner = runner
        self._context = context
        self._working: dict[str, asyncio.Task] = {}
        # Those the user stopped, and those whose conversation was deleted, while their work winds down.
        self._stopping: set[str] = set()
        self._forgetting: set[str] = set()
        # Those telling their end, which a stop mustn't cut short; and the deleted conversations.
        self._finishing: set[str] = set()
        self._gone: set[str] = set()
        self._added = asyncio.Event()

    async def start(
        self, task: str, user_id: str, thread_id: str, channel: str, plugins: Collection[str], agent: str = ""
    ) -> str:
        if thread_id in self._gone:
            raise SubagentError(said("That conversation was deleted."))
        await self._runner().background_graph(agent)  # an unknown agent raises before anything is kept
        started = datetime.now(UTC).isoformat()
        subagent = BackgroundSubagent(
            uuid.uuid4().hex[:8], user_id, thread_id, channel, task, agent, [*plugins], started
        )
        await records.save(self._storage.store, subagent)
        publish(self._bus, subagent)
        self._added.set()
        return subagent.id

    async def run(self, stop: asyncio.Event) -> None:
        try:
            while not stop.is_set():
                self._added.clear()
                await self._work_on_kept()
                await first(stop.wait(), self._added.wait())
        finally:
            await self._wind_down(list(self._working.values()))

    async def listed(self, thread_id: str = "") -> list[BackgroundSubagent]:
        """Every one, or the conversation's, the newest first."""
        return await records.listed(self._storage.store, thread_id)

    async def details(self, subagent_id: str) -> tuple[BackgroundSubagent, list[BackgroundStep]]:
        """Raises SubagentError for an unknown one."""
        return await self._known(subagent_id), await records.steps(self._storage.store, subagent_id)

    async def answer(self, subagent_id: str, interrupt_id: str, decision: dict[str, Any]) -> bool:
        """Answers what it waits for. False when it doesn't wait for that (answered already, or ended). Raises
        SubagentError for an unknown one."""
        subagent = await self._known(subagent_id)
        if not any(asked.interrupt_id == interrupt_id for asked in subagent.waiting):
            return False
        return self._approvals.answer(interrupt_id, decision)

    async def stop(self, subagent_id: str) -> BackgroundSubagent:
        """Returns once it's stopped. Raises SubagentError for an unknown one or one that ended."""
        subagent = await self._known(subagent_id)
        working = self._working.get(subagent_id)
        if subagent.ended or working is None or working.done() or subagent_id in self._finishing:
            raise SubagentError(said("That subagent isn't working."))
        self._stopping.add(subagent_id)
        working.cancel()
        await asyncio.wait([working])
        self._stopping.discard(subagent_id)
        return await self._known(subagent_id)

    async def remove(self, subagent_id: str) -> None:
        """Its card goes from the apps. Raises SubagentError for an unknown one or one still working."""
        if not (await self._known(subagent_id)).ended:
            raise SubagentError(said("That subagent is still working: stop it first."))
        await records.delete(self._storage.store, subagent_id)
        self._bus.publish("subagents", id=subagent_id, thread_id="", status="removed")

    async def forget(self, thread_id: str) -> None:
        """The conversation was deleted: its subagents stop and go, with all they kept."""
        self._gone.add(thread_id)  # none starts or tells its end in it from now on
        kept = await records.listed(self._storage.store, thread_id)
        working = [self._working[s.id] for s in kept if s.id in self._working]
        self._forgetting.update(s.id for s in kept)
        await self._wind_down(working)
        for subagent in kept:
            await self._discard(subagent.id)
            await records.delete(self._storage.store, subagent.id)
            self._forgetting.discard(subagent.id)

    async def _known(self, subagent_id: str) -> BackgroundSubagent:
        subagent = await records.load(self._storage.store, subagent_id)
        if subagent is None:
            raise SubagentNotFoundError(said("No subagent {id}.", id=subagent_id))
        return subagent

    async def _work_on_kept(self) -> None:
        self._working = {key: task for key, task in self._working.items() if not task.done()}
        for subagent in await records.listed(self._storage.store):
            if not subagent.ended and subagent.id not in self._working and subagent.thread_id not in self._gone:
                self._working[subagent.id] = asyncio.create_task(self._work(subagent), name=f"subagent {subagent.id}")

    async def _work(self, subagent: BackgroundSubagent) -> None:
        work = SubagentWork(subagent, self._storage.store, self._bus, self._health, self._answers)
        context = replace(self._context(subagent.user_id, subagent.channel), subagents=None, background=None)
        try:
            result = await work.answer(self._runner(), context)
        except asyncio.CancelledError:
            if subagent.id in self._forgetting:
                return
            if subagent.id not in self._stopping:
                raise  # the daemon is stopping: it goes on when it starts again
            await self._end(work, STOPPED, "")
        except Exception as e:
            logger.exception("Background subagent %s failed", subagent.id)
            await self._finish(work, FAILED, f"{type(e).__name__}: {i18n.message(e)}")
        else:
            await self._finish(work, DONE, result)

    async def _finish(self, work: SubagentWork, status: Status, result: str) -> None:
        """Ends it with no stop cutting that short, which would tell its end twice."""
        self._finishing.add(work.subagent.id)
        try:
            await self._end(work, status, result)
        finally:
            self._finishing.discard(work.subagent.id)

    async def _answers(self, subagent: BackgroundSubagent, asked: list[ApprovalRequired]) -> dict[str, Any]:
        t = await i18n.chosen(self._storage.store)
        title = t("The subagent working on “{task}”", task=short(subagent.task, _ASKED_TITLE))
        waits = [self._approvals.wait(a.interrupt_id, title, a.request, _forwarded(subagent, a)) for a in asked]
        decisions = await asyncio.gather(*waits)
        return {a.interrupt_id: d for a, d in zip(asked, decisions, strict=True)}

    async def _end(self, work: SubagentWork, status: Status, result: str) -> None:
        """Told before it's kept as ended, so a daemon stopping in between tells it again when it starts (its
        checkpoints say it's done), rather than not at all. Its checkpoints go once it's kept."""
        subagent = work.subagent
        subagent.status, subagent.result, subagent.ended_at = status, result, datetime.now(UTC).isoformat()
        subagent.step, subagent.waiting = "", []
        try:
            await self._tell(subagent)
        except Exception:
            logger.exception("Couldn't tell the end of background subagent %s", subagent.id)
        await work.save()
        await self._discard(subagent.id)
        await self._keep_latest(subagent.thread_id)

    async def _tell(self, subagent: BackgroundSubagent) -> None:
        if subagent.thread_id in self._gone:
            return
        told = ends.ended(subagent)
        store = self._storage.store
        if subagent.status == STOPPED:
            await ended.record(store, subagent.user_id, subagent.thread_id, told.key, told.note)
            return
        await self._ends.deliver(Origin(subagent.user_id, subagent.thread_id, subagent.channel), told)

    async def _discard(self, subagent_id: str) -> None:
        """Its checkpoints, and the files its tools brought, which nothing else refers to: its answer is text."""
        config = RunnableConfig(configurable={"thread_id": thread(subagent_id)})
        saved = await self._storage.checkpointer.aget_tuple(config)
        messages: list[BaseMessage] = list(saved.checkpoint["channel_values"].get("messages", [])) if saved else []
        for path in upload_paths(messages):
            await asyncio.to_thread(uploads.delete, path)
        await self._storage.checkpointer.adelete_thread(thread(subagent_id))

    async def _keep_latest(self, thread_id: str) -> None:
        ended_ones = [s for s in await records.listed(self._storage.store, thread_id) if s.ended]
        for subagent in ended_ones[KEPT_ENDED:]:
            await records.delete(self._storage.store, subagent.id)

    async def _wind_down(self, working: list[asyncio.Task]) -> None:
        for task in working:
            task.cancel()
        for task in working:
            with contextlib.suppress(asyncio.CancelledError):
                await task


def _forwarded(subagent: BackgroundSubagent, asked: ApprovalRequired) -> list[str]:
    """An approval goes to the chat channel its conversation is on too; a server's form shows only in the apps."""
    return [] if asked.request.get("kind") else [subagent.channel]
