"""Coding tasks beside the conversation that started them. The assistant's start_task runs the task in the background
and the conversation stays the assistant's: the user goes on talking to it while the agent works, and the web app shows
the agent's work in a panel beside the chat, a tab per session (beside_records.py), live: each step the agent writes is
an `agent_task_step` event, with its place among the task's steps, and each time it says how full its context is an
`agent_task_context` event, which the panel's status line shows with its model. The user writes to the agent from
there: while it works, a worker that takes messages gets it between its steps (docs/agent-plugins.md); otherwise, and
once its task ended, it goes to the agent as the next task of the same session (follow_up_of), so the agent goes on with
what it knows. The daemon runs this as a supervised task that follows each session's last task to its end and sends on
what the user wrote that the agent didn't take.

The task the assistant started tells its end to the conversation (ends.py), where the assistant follows it up with a
short summary; a task the user started from the panel isn't told, as the user watched it there. While tasks run, the
turn header of each user message lists them (`note`), so the assistant knows how they're going."""

import asyncio
import contextlib
import logging
from dataclasses import asdict, dataclass, field
from typing import Literal

from langgraph.store.base import BaseStore

from lo9i.core.agent_tasks import beside_records as records
from lo9i.core.agent_tasks.beside_records import BesideSession
from lo9i.core.agent_tasks.records import Context, Status, Task, TaskState
from lo9i.core.agent_tasks.reports import TaskReports
from lo9i.core.agent_tasks.service import AgentTaskError, AgentTasks
from lo9i.core.agent_tasks.steps import line, parse, streamed, waiting
from lo9i.core.agent_tasks.waiting import Measured, Report
from lo9i.core.background import Origin
from lo9i.core.bus import EventBus
from lo9i.core.config import settings
from lo9i.core.conversation import prompts
from lo9i.core.conversation.turn_header import note_block
from lo9i.core.i18n import said
from lo9i.core.waiting import first

logger = logging.getLogger(__name__)

# What became of a message the user wrote the agent: it has it ("taken", shown among its steps until it gets to it),
# it waits for the task to end to go as the next one ("later"), or it started the next task ("started").
Sent = Literal["taken", "later", "started"]


class TasksBesideError(Exception):
    """What the user asked of a session can't be done now. The text says why, for the user."""


class SessionNotFoundError(TasksBesideError):
    pass


@dataclass
class TaskStep:
    """One step a task wrote (docs/agent-plugins.md): `kind` and the fields it has."""

    kind: str
    text: str = ""
    tool: str = ""
    detail: str = ""
    id: str = ""
    # The tool call whose subagent took it.
    within: str = ""
    # A message the user sent that the agent hasn't got to yet.
    waiting: bool = False
    # When its worker wrote it (ISO 8601), which the panel shows a tool call with; "" when the worker doesn't say.
    at: str = ""


@dataclass
class TaskTurn:
    """One task of a session."""

    id: str
    # What the agent was asked: the assistant's brief, or what the user wrote it.
    asked: str
    from_user: bool
    status: Status
    started_at: str
    finished_at: str = ""
    # Its final answer, or what went wrong, once it ended.
    result: str = ""
    cost_usd: float | None = None
    # What it wrote, oldest first, without the words streamed before each whole block.
    steps: list[TaskStep] = field(default_factory=list)
    # The messages the user sent it that its worker hasn't passed on to the agent yet, which no step shows yet.
    unread: list[TaskStep] = field(default_factory=list)


@dataclass
class TaskSession:
    """A tab of the panel: an agent's session started from the conversation."""

    id: str
    # The plugin that brings the agent, and the agent's name.
    agent: str
    name: str
    title: str
    repository: str
    # Its last task's.
    status: Status
    started_at: str
    # What its last task is doing now, one line, while it runs.
    step: str = ""
    # How many messages wait to go to the agent as its next task.
    waiting: int = 0
    # How full the agent's context is, of its model's window, and the model, as its last task last said (the one
    # before until it says); 0 and "" when its worker doesn't say.
    context_tokens: int = 0
    context_limit: int = 0
    model: str = ""
    # The conversation that started it.
    thread_id: str = ""


@dataclass
class TaskSessionDetails:
    session: TaskSession
    # Its tasks, oldest first.
    turns: list[TaskTurn]
    # What the user wrote that waits to go to the agent as its next task.
    waiting: list[str]


class TasksBeside:
    name = "tasks beside"

    def __init__(self, tasks: AgentTasks, reports: TaskReports, store: BaseStore, bus: EventBus) -> None:
        self._tasks = tasks
        self._reports = reports
        self._store = store
        self._bus = bus
        # Held while a session's tasks change: a message the user sends and the end of its last task never both
        # start the next one.
        self._lock = asyncio.Lock()
        self._following: dict[str, asyncio.Task] = {}

    async def started(self, origin: Origin, task: Task, agent: str, title: str) -> None:
        """The assistant started `task` from the conversation (start_task): a session of its own, or the next task of
        the session it follows up when that one is here."""
        name = next((a.name for a in self._tasks.agents() if a.server == agent), agent)
        async with self._lock:
            sessions = await records.of(self._store, origin.user_id, origin.thread_id)
            if (session := records.find(sessions, task.session)) is not None:
                session.tasks.append(task.id)
                session.following = True
            else:
                sessions.append(BesideSession(task.session, agent, name, title, task.repository, [task.id]))
            await records.save(self._store, origin.user_id, origin.thread_id, sessions)

    async def listed(self, user_id: str, thread_id: str) -> list[TaskSession]:
        """The conversation's sessions, oldest first; not those whose agent's plugin isn't installed now."""
        listed = [await self._listed(thread_id, s) for s in await records.of(self._store, user_id, thread_id)]
        return [session for session in listed if session is not None]

    async def everywhere(self, user_id: str) -> list[TaskSession]:
        """Every conversation's sessions, the newest first; not those whose agent's plugin isn't installed now."""
        every = (await records.every(self._store, user_id)).items()
        listed = [await self._listed(thread_id, s) for thread_id, sessions in every for s in sessions]
        found = [session for session in listed if session is not None]
        return sorted(found, key=lambda s: s.started_at, reverse=True)

    async def details(self, user_id: str, thread_id: str, session_id: str) -> TaskSessionDetails:
        """Raises SessionNotFoundError for an unknown session, or one whose agent's plugin isn't installed now."""
        session = await self._session(user_id, thread_id, session_id)
        listed = await self._listed(thread_id, session)
        if listed is None:
            raise SessionNotFoundError(said("{agent}'s plugin isn't installed now.", agent=session.name))
        turns = [await self._turn(session, task_id) for task_id in session.tasks]
        return TaskSessionDetails(listed, turns, list(session.waiting))

    async def send(self, user_id: str, thread_id: str, session_id: str, text: str) -> Sent:
        """What the user wrote the agent: between its steps while it works and its worker takes messages, else as the
        next task of the session, once the one running ends or now; one written before its worker takes messages goes
        to it once it does. Raises SessionNotFoundError for an unknown session,
        TasksBesideError when the next task can't start."""
        async with self._lock:
            sessions = await records.of(self._store, user_id, thread_id)
            session = _found(sessions, session_id)
            last = session.tasks[-1]
            if await self._running(last):
                if not await self._tasks.takes_messages(last):
                    session.waiting.append(text)
                    await records.save(self._store, user_id, thread_id, sessions)
                    return "later"
                # Refused only when it ended meanwhile: then it's the next task.
                if await self._told(thread_id, session, last, text):
                    return "taken"
            try:
                await self._go_on(session, [text])
            finally:
                await records.save(self._store, user_id, thread_id, sessions)
            return "started"

    async def stop(self, user_id: str, thread_id: str, session_id: str) -> TaskSession:
        """Stops the session's task in progress, which the user did: its end isn't told to the conversation. What the
        user sent that it hadn't taken goes on as the next task. Raises TasksBesideError when none is working."""
        session = await self._session(user_id, thread_id, session_id)
        last = session.tasks[-1]
        if not await self._running(last):
            raise TasksBesideError(said("{agent} isn't working on anything.", agent=session.name))
        async with self._reports.reading(last):
            await self._tasks.stop(last)
            await self._reports.seen(last, None)
        listed = await self._listed(thread_id, session)
        if listed is None:
            raise SessionNotFoundError(said("{agent}'s plugin isn't installed now.", agent=session.name))
        return listed

    async def remove(self, user_id: str, thread_id: str, session_id: str) -> None:
        """Takes a session off the panel; its tasks' records stay with the agent. Raises TasksBesideError while it
        works."""
        async with self._lock:
            sessions = await records.of(self._store, user_id, thread_id)
            session = _found(sessions, session_id)
            if await self._running(session.tasks[-1]):
                raise TasksBesideError(said("{agent} is still working. Stop it first.", agent=session.name))
            await records.save(self._store, user_id, thread_id, [s for s in sessions if s is not session])

    async def thread_of(self, user_id: str, task_id: str) -> str:
        """The conversation whose panel shows the task; "" when none does."""
        for thread_id, sessions in (await records.every(self._store, user_id)).items():
            if any(task_id in session.tasks for session in sessions):
                return thread_id
        return ""

    async def note(self, user_id: str, thread_id: str) -> list[dict[str, str]]:
        """The turn header note of the conversation's tasks still running, for the assistant; nothing when none is."""
        running = []
        for session in await records.of(self._store, user_id, thread_id):
            if session.following and (state := await self._state(session.tasks[-1])) and state.status == "running":
                running.append(_running_line(session, state))
        if not running:
            return []
        return [note_block(prompts.load("tasks_beside").format(tasks="\n".join(running)))]

    async def run(self, stop: asyncio.Event) -> None:
        try:
            while not stop.is_set():
                # Taken before reading, so a session changed meanwhile is read again.
                after = self._bus.last_id
                await self._follow_all()
                await first(stop.wait(), self._next_change(after))
        finally:
            await self._stop_following()

    async def _follow_all(self) -> None:
        self._following = {task_id: f for task_id, f in self._following.items() if not f.done()}
        for thread_id, sessions in (await records.every(self._store, settings.owner_id)).items():
            for session in sessions:
                last = session.tasks[-1]
                if session.following and last not in self._following:
                    self._following[last] = asyncio.create_task(self._follow(thread_id, session.id, last))

    async def _follow(self, thread_id: str, session_id: str, task_id: str) -> None:
        """Its steps from now on are events; once it ended, what the user sent it that it didn't take goes on."""
        try:
            lines, steps = await self._tasks.written(task_id)
            report = self._steps(thread_id, session_id, task_id, steps)
            await self._tasks.ended(task_id, report, lines, self._measured(thread_id, session_id))
        except AgentTaskError:
            # Its agent isn't installed now; it's followed again when a session changes or the daemon starts.
            return
        try:
            await self._settle(settings.owner_id, thread_id, session_id, task_id)
        except Exception:
            logger.exception("Couldn't go on after task %s", task_id)

    def _steps(self, thread_id: str, session_id: str, task_id: str, before: int) -> Report:
        """Each step after the first `before`, with its place among the task's steps, so the apps put it where it goes
        after the ones they read; not the words of one as they stream: those come again whole."""
        index = before

        async def _report(message: str) -> None:
            nonlocal index
            if streamed(message):
                return
            where = {"thread_id": thread_id, "session_id": session_id, "task_id": task_id, "index": index}
            self._bus.publish("agent_task_step", **where, step=asdict(_step(message)))
            index += 1
            await self._pass_on_waiting(settings.owner_id, thread_id, session_id, task_id)

        return _report

    def _measured(self, thread_id: str, session_id: str) -> Measured:
        def _tell() -> None:
            self._bus.publish("agent_task_context", thread_id=thread_id, session_id=session_id)

        return _tell

    async def _pass_on_waiting(self, user_id: str, thread_id: str, session_id: str, task_id: str) -> None:
        """What the user wrote before its worker took messages goes to it once it does (it makes its inbox when it's
        ready, docs/agent-plugins.md), instead of waiting for the task to end."""
        async with self._lock:
            sessions = await records.of(self._store, user_id, thread_id)
            session = records.find(sessions, session_id)
            if session is None or not session.waiting or session.tasks[-1] != task_id:
                return
            if not await self._tasks.takes_messages(task_id):
                return
            while session.waiting and await self._told(thread_id, session, task_id, session.waiting[0]):
                session.waiting.pop(0)
            await records.save(self._store, user_id, thread_id, sessions)

    async def _told(self, thread_id: str, session: BesideSession, task_id: str, text: str) -> bool:
        """`text` went to the running task; False when it ended meanwhile, so it goes as the next one."""
        try:
            await self._tasks.message(task_id, text, text, [])
        except AgentTaskError:
            return False
        # It shows among the task's messages not passed on yet, until its worker's step for it.
        self._bus.publish("tasks_beside", thread_id=thread_id, session_id=session.id)
        return True

    async def _settle(self, user_id: str, thread_id: str, session_id: str, task_id: str) -> None:
        """Once `task_id` ended: the next task with what the user sent that it didn't take, or nothing to follow. A
        message the user sent meanwhile may have started the next one already."""
        async with self._lock:
            sessions = await records.of(self._store, user_id, thread_id)
            session = records.find(sessions, session_id)
            if session is None or not session.following or session.tasks[-1] != task_id:
                return
            try:
                await self._go_on(session, [])
            except TasksBesideError as e:
                logger.warning("Couldn't send on what was written to %s's task %s: %s", session.name, task_id, e)
            await records.save(self._store, user_id, thread_id, sessions)

    async def _go_on(self, session: BesideSession, written: list[str]) -> None:
        """After its last task ended: the next task of the session with what its agent didn't take, what waited and
        what was just `written`, or nothing more to follow when there's none. A task that can't start leaves them
        waiting, raising TasksBesideError."""
        last = session.tasks[-1]
        try:
            untaken = [str(m.get("text", "")) for m in await self._tasks.take_untaken(last)]
        except AgentTaskError:
            untaken = []
        texts = [text for text in [*untaken, *session.waiting, *written] if text.strip()]
        session.waiting, session.following = [], False
        if not texts:
            return
        try:
            task = await self._tasks.start(session.agent, session.repository, "\n\n".join(texts), last)
        except AgentTaskError as e:
            session.waiting = texts
            raise TasksBesideError(str(e)) from e
        session.tasks.append(task.id)
        session.from_user.append(task.id)
        session.following = True

    async def _next_change(self, after: int) -> None:
        async for event in self._bus.subscribe(after):
            if event.kind == "tasks_beside":
                return

    async def _stop_following(self) -> None:
        for following in self._following.values():
            following.cancel()
        for following in self._following.values():
            with contextlib.suppress(asyncio.CancelledError):
                await following
        self._following = {}

    async def _session(self, user_id: str, thread_id: str, session_id: str) -> BesideSession:
        return _found(await records.of(self._store, user_id, thread_id), session_id)

    async def _listed(self, thread_id: str, session: BesideSession) -> TaskSession | None:
        first_state, last_state = await self._state(session.tasks[0]), await self._state(session.tasks[-1])
        if first_state is None or last_state is None:
            return None
        context = await self._context(session.tasks[-1]) or Context(0, 0)
        return TaskSession(
            session.id,
            session.agent,
            session.name,
            session.title,
            session.repository,
            last_state.status,
            first_state.task.started_at,
            _latest(last_state) if last_state.status == "running" else "",
            len(session.waiting),
            context.tokens,
            context.window,
            context.model,
            thread_id,
        )

    async def _turn(self, session: BesideSession, task_id: str) -> TaskTurn:
        state = await self._tasks.state(task_id)
        task, outcome = state.state.task, state.state.outcome
        turn = TaskTurn(task.id, task.prompt, task.id in session.from_user, state.state.status, task.started_at)
        turn.steps = [_step(message) for message in await self._tasks.steps(task_id)]
        if state.state.status == "running":
            unread = await self._tasks.not_passed_on(task_id)
            turn.unread = [TaskStep("user", str(m.get("text", "")), id=i, waiting=True) for i, m in unread]
        if outcome is not None:
            turn.finished_at, turn.result, turn.cost_usd = outcome.finished_at, outcome.text, outcome.cost_usd
        return turn

    async def _state(self, task_id: str) -> TaskState | None:
        try:
            return (await self._tasks.state(task_id)).state
        except AgentTaskError:
            return None

    async def _context(self, task_id: str) -> Context | None:
        try:
            return await self._tasks.task_context(task_id)
        except AgentTaskError:
            return None

    async def _running(self, task_id: str) -> bool:
        state = await self._state(task_id)
        return state is not None and state.status == "running"


def _found(sessions: list[BesideSession], session_id: str) -> BesideSession:
    session = records.find(sessions, session_id)
    if session is None:
        raise SessionNotFoundError(said("No coding session {session_id} here.", session_id=session_id))
    return session


def _step(message: str) -> TaskStep:
    fields = parse(message)
    return TaskStep(
        fields.get("kind", "note"),
        fields.get("text", ""),
        fields.get("tool", ""),
        fields.get("detail", ""),
        fields.get("id", ""),
        fields.get("within", ""),
        waiting(fields),
        fields.get("at", ""),
    )


def _latest(state: TaskState) -> str:
    lines = [text for step in state.progress if (text := line(step))]
    return lines[-1] if lines else ""


def _running_line(session: BesideSession, state: TaskState) -> str:
    task = state.task
    doing = f"; latest step: {latest}" if (latest := _latest(state)) else ""
    return (
        f'- {session.name}, "{session.title}" in {session.repository}: task {task.id}, running since '
        f"{task.started_at}{doing}"
    )
