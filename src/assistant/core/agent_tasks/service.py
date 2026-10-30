"""The coding agents installed plugins bring, and their tasks. Each task runs in the plugin's worker,
started detached with the plugin's env, keys and login (docs/agent-plugins.md); its records live in the
plugin's data folder (records.py), so tasks outlive a restart of the daemon."""

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from langgraph.store.base import BaseStore
from mcp.client.stdio import get_default_environment

from assistant.core import uploads
from assistant.core.agent_tasks import sent, workers
from assistant.core.agent_tasks.records import Context, Task, TaskState, TaskStore, lost
from assistant.core.agent_tasks.sessions import Sessions
from assistant.core.agent_tasks.steps import Upload
from assistant.core.agent_tasks.waiting import Measured, Report, at_most, until_ended
from assistant.core.config import settings
from assistant.core.mcp import data_key, folders, keys, logins, servers, ssh_agent
from assistant.core.mcp.environment import Environments
from assistant.core.mcp.logins import SharedLogins
from assistant.core.mcp.servers import McpServer, McpServerError
from assistant.core.secret_store import SecretBox

# The longest a status call waits for a task to finish.
MAX_WAIT_SECONDS = 600

# Where the files the user sends an agent are saved, given to its worker (docs/agent-plugins.md).
UPLOADS_ENV = "LO9I_UPLOADS"


class AgentTaskError(Exception):
    """A task couldn't start, wasn't found, or ended without a reply. The text says why, for the user."""


@dataclass(frozen=True)
class CodingAgent:
    # The plugin it comes with.
    server: str
    name: str
    # Its command in the apps (/claude), which hands a conversation to it.
    command: str = ""


@dataclass(frozen=True)
class FoundTask:
    agent: CodingAgent
    state: TaskState


class AgentTasks:
    def __init__(self, store: BaseStore, secrets: SecretBox, environments: Environments, shared: SharedLogins) -> None:
        self._store = store
        self._secrets = secrets
        self._environments = environments
        self._shared = shared
        self._agents: dict[str, McpServer] = {}
        # Held while a message is written to a task's inbox, and while the messages a task ended without
        # taking are read: a message is then either among them or refused as sent to a task that has ended.
        self._inboxes = asyncio.Lock()

    async def reload(self) -> None:
        """Brings the agents in line with the saved plugins. Called after every change."""
        found = [s for s in await servers.load_all(self._store) if s.enabled and s.agent_worker]
        self._agents = {s.name: s for s in found}

    def agents(self) -> list[CodingAgent]:
        """The installed agents, by plugin name: what the task tools offer."""
        return [_coding_agent(s) for _, s in sorted(self._agents.items())]

    def trusted(self, agent: str) -> bool:
        """The user trusts the plugin: its tasks start and stop without asking."""
        server = self._agents.get(agent)
        return server is not None and server.trusted

    async def start(self, agent: str, repository: str, prompt: str, follow_up_of: str = "") -> Task:
        """Raises AgentTaskError for an unknown agent, a folder that doesn't exist or a follow-up of a
        task still running."""
        server = self._agent(agent)
        folder = _existing_folder(repository)
        session = await self._session_to_continue(server, follow_up_of) if follow_up_of else ""
        tasks = _tasks(server)
        task = await asyncio.to_thread(tasks.create, str(folder), prompt, session, follow_up_of)
        await self._launch(server, tasks, task)
        return task

    async def state(self, task_id: str) -> FoundTask:
        """Raises AgentTaskError for an unknown task."""
        server = await self._owner(task_id)
        return FoundTask(_coding_agent(server), await asyncio.to_thread(_tasks(server).state, task_id))

    async def conversation(self, task_id: str) -> str:
        """The conversation handed to the agent that the task answers in; "" for a task started with
        start_task. Raises AgentTaskError for an unknown task."""
        server = await self._owner(task_id)
        return await asyncio.to_thread(_tasks(server).conversation, task_id)

    async def wait(self, task_id: str, seconds: int, report: Report | None = None) -> FoundTask:
        """The task's state once it ends or `seconds` pass. `report` gets each step it has written and
        writes meanwhile. Raises AgentTaskError for an unknown task."""
        server = await self._owner(task_id)
        await at_most(_tasks(server), task_id, min(seconds, MAX_WAIT_SECONDS), report)
        return await self.state(task_id)

    async def ended(self, task_id: str, report: Report | None = None) -> FoundTask:
        """The task's state once it ends, however long that takes. `report` gets each step it has written
        and writes meanwhile. Raises AgentTaskError for an unknown task, or one whose agent isn't installed now."""
        server = await self._owner(task_id)
        await until_ended(_tasks(server), task_id, report)
        return await self.state(task_id)

    async def recent(self) -> list[FoundTask]:
        """The latest tasks of every agent, newest first."""
        found = [task for server in self._agents.values() for task in await self._recent(server)]
        return sorted(found, key=lambda f: f.state.task.started_at, reverse=True)

    async def stop(self, task_id: str) -> FoundTask:
        """Stops a running task and every command it started. Raises AgentTaskError for an unknown task."""
        server = await self._owner(task_id)
        await _stop(_tasks(server), task_id)
        return await self.state(task_id)

    async def message(self, task_id: str, text: str, said: str, files: list[Upload]) -> None:
        """Passes `text` on to a running task, whose agent takes it between its steps; its step shows what
        the user `said` and the `files` they sent instead (sent.py). Raises AgentTaskError for an unknown task,
        one that isn't running, or an agent that takes no messages while it works."""
        await self._tell(task_id, sent.message(text, said, files))

    async def interrupt(self, task_id: str) -> None:
        """Stops the step a running task is taking; it then waits for the user's next message. Raises
        AgentTaskError as `message` does."""
        await self._tell(task_id, {"kind": "interrupt"})

    async def context(self, agent: str, conversation: str, folder: str) -> Context | None:
        """How full the agent's context is in the conversation's session in `folder`, as its latest task last said,
        while it runs too. None before it says, when its worker doesn't, or for an agent that's gone."""
        server = self._agents.get(agent)
        if server is None:
            return None
        tasks, where = _tasks(server), str(Path(folder).expanduser())
        last = await asyncio.to_thread(_sessions(server).last, conversation, where, tasks)
        return await asyncio.to_thread(tasks.context, last.id) if last else None

    async def working_in(self, agent: str, conversation: str, folder: str) -> str:
        """The id of the task running for the conversation in `folder`; "" when none is."""
        server = self._agent(agent)
        tasks = _tasks(server)
        last = await asyncio.to_thread(_sessions(server).last, conversation, folder, tasks)
        if last is None or (await asyncio.to_thread(tasks.state, last.id, 0)).status != "running":
            return ""
        return last.id

    async def converse(
        self, agent: str, conversation: str, folder: str, message: str, report: Report, measured: Measured
    ) -> str:
        """Answers `message` in `folder`, continuing what was said in this conversation there, and returns
        the reply. `report` gets each step as the worker writes it, and a `user` step for each message sent
        to the task that it ended without taking, however it ended, so the conversation keeps what the user
        sent; `measured` hears each time the agent says how full its context is now (`context`). After a task
        that's done they're answered next, in the same session. Cancelling stops the task. Raises
        AgentTaskError when it can't start or ends without a reply."""
        server, where = self._agent(agent), str(_existing_folder(folder))
        task = await self._next_in_conversation(server, conversation, where, message)
        while True:
            state, left = await self._answered(_tasks(server), task.id, report, measured)
            if state.status != "done" or not left:
                return _reply(state)
            task = await self._next_in_conversation(server, conversation, where, "\n\n".join(m["text"] for m in left))

    async def _answered(
        self, tasks: TaskStore, task_id: str, report: Report, measured: Measured
    ) -> tuple[TaskState, list[dict[str, Any]]]:
        """The task's state once it ends, and the messages it ended without taking; stopping the wait stops
        the task, and the steps it wrote that weren't read yet and its untaken messages are reported all the same."""
        followed = _Followed(_as_sent(tasks, task_id, report))
        try:
            state = await until_ended(tasks, task_id, followed, measured)
        except BaseException:
            await _stop(tasks, task_id)
            await followed.rest(tasks, task_id)
            await self._untaken(tasks, task_id, report, answered_next=False)
            raise
        return state, await self._untaken(tasks, task_id, report, answered_next=state.status == "done")

    async def _untaken(
        self, tasks: TaskStore, task_id: str, report: Report, answered_next: bool
    ) -> list[dict[str, Any]]:
        """Once the task has ended: read under the lock `_tell` writes under, after which no message reaches it. Those
        its worker never passed on are reported as `user` steps, waiting unless they're `answered_next` in the same
        run; the others already were."""
        async with self._inboxes:
            left = await asyncio.to_thread(tasks.untaken, task_id)
        for untaken in left:
            if not untaken.passed_on:
                await report(sent.user_step(untaken.message, waiting=not answered_next))
        return [untaken.message for untaken in left]

    async def take_waiting(self, agent: str, conversation: str, folder: str) -> list[dict[str, Any]]:
        """The messages sent to the conversation's last task in `folder` that its agent hadn't taken when it ended,
        oldest first, as written in its inbox (sent.py), for the agent to get next: once, so a run that fails before
        it starts a task of its own doesn't send them again. [] while it runs, or for an agent that's gone."""
        server = self._agents.get(agent)
        if server is None:
            return []
        tasks, where = _tasks(server), str(Path(folder).expanduser())
        last = await asyncio.to_thread(_sessions(server).last, conversation, where, tasks)
        if last is None or (await asyncio.to_thread(tasks.state, last.id, 0)).status == "running":
            return []
        async with self._inboxes:
            if await asyncio.to_thread(tasks.sent_on, last.id):
                return []
            left = await asyncio.to_thread(tasks.untaken, last.id)
            await asyncio.to_thread(tasks.mark_sent_on, last.id)
        return [untaken.message for untaken in left]

    async def _tell(self, task_id: str, message: dict[str, Any]) -> None:
        """The check that it runs and the write are one step for `_untaken`: a task that ends in between still
        has the message among those it didn't take, which its conversation answers next."""
        server = await self._owner(task_id)
        tasks = _tasks(server)
        async with self._inboxes:
            if (await asyncio.to_thread(tasks.state, task_id, 0)).status != "running":
                raise AgentTaskError(f"{server.agent_name} has already finished that task.")
            if not await asyncio.to_thread(tasks.takes_messages, task_id):
                raise AgentTaskError(f"{server.agent_name} can't take messages while it works. Wait for it to finish.")
            await asyncio.to_thread(tasks.add_message, task_id, message)
        if (pid := await asyncio.to_thread(tasks.pid, task_id)) is not None:
            await asyncio.to_thread(workers.wake, pid)

    async def _next_in_conversation(self, server: McpServer, conversation: str, folder: str, message: str) -> Task:
        tasks, sessions = _tasks(server), _sessions(server)
        previous = await asyncio.to_thread(sessions.last, conversation, folder, tasks)
        if previous is not None and (await asyncio.to_thread(tasks.state, previous.id, 0)).status == "running":
            raise AgentTaskError("Still working on the previous message. Wait for it, or stop it first.")
        session, follows = (previous.session, previous.id) if previous else ("", "")
        task = await asyncio.to_thread(tasks.create, folder, message, session, follows)
        await asyncio.to_thread(tasks.mark_conversation, task.id, conversation)
        await self._launch(server, tasks, task)
        await asyncio.to_thread(sessions.record, conversation, folder, task)
        return task

    async def _launch(self, server: McpServer, tasks: TaskStore, task: Task) -> None:
        """The worker runs with the plugin's env, keys and data key, its login (core/mcp/logins.py), the time zone and
        the uploads folder, in the plugin's folder, from its own environment."""
        own = await data_key.with_key(self._store, self._secrets, await keys.fill(self._store, self._secrets, server))
        filled = ssh_agent.with_agent(logins.with_login(own, self._shared()))
        try:
            await self._environments.ensure(server.name, server.agent_worker)
        except McpServerError as e:
            raise AgentTaskError(str(e)) from e
        # The files the user sends the agent are saved there (core/agent/messaging.py::_to_agent): an agent that
        # checks the paths it opens is let into it.
        shared = {"TZ": settings.timezone, UPLOADS_ENV: str(uploads.absolute(""))}
        env = get_default_environment() | shared | filled.env
        code = folders.code(server.name)
        command = [server.agent_worker, *server.agent_args]
        await asyncio.to_thread(workers.start, command, tasks.folder(task.id), env, code if code.is_dir() else None)

    async def _session_to_continue(self, server: McpServer, task_id: str) -> str:
        found = await self.state(task_id)
        if found.agent.server != server.name:
            raise AgentTaskError(f"Task {task_id} is {found.agent.name}'s: follow it up with {found.agent.name}.")
        if found.state.status == "running":
            raise AgentTaskError(f"Task {task_id} is still running. Wait for it or stop it before following up.")
        return found.state.task.session

    async def _owner(self, task_id: str) -> McpServer:
        for server in self._agents.values():
            if await asyncio.to_thread(_tasks(server).has, task_id):
                return server
        raise AgentTaskError(f"No task {task_id}. list_tasks shows the latest ones.")

    async def _recent(self, server: McpServer) -> list[FoundTask]:
        tasks = _tasks(server)
        recent = await asyncio.to_thread(tasks.recent)
        states = [await asyncio.to_thread(tasks.state, t.id, 0) for t in recent]
        return [FoundTask(_coding_agent(server), state) for state in states]

    def _agent(self, name: str) -> McpServer:
        server = self._agents.get(name)
        if server is None:
            installed = ", ".join(self._agents) or "none"
            raise AgentTaskError(f"No coding agent {name!r}. Installed: {installed}.")
        return server


def _coding_agent(server: McpServer) -> CodingAgent:
    return CodingAgent(server.name, server.agent_name, server.agent_command)


def _tasks(server: McpServer) -> TaskStore:
    return TaskStore(folders.data(server.name) / "tasks")


def _sessions(server: McpServer) -> Sessions:
    return Sessions(folders.data(server.name) / "conversations")


def _existing_folder(path: str) -> Path:
    folder = Path(path).expanduser()
    if not folder.is_absolute() or not folder.is_dir():
        raise AgentTaskError(f"{path} isn't an existing folder. Give an absolute path.")
    return folder


async def _stop(tasks: TaskStore, task_id: str) -> None:
    await asyncio.to_thread(tasks.mark_stopped, task_id)
    if (pid := await asyncio.to_thread(tasks.pid, task_id)) is not None:
        await asyncio.to_thread(workers.stop, pid)


def _as_sent(tasks: TaskStore, task_id: str, report: Report) -> Report:
    """`report` with each `user` step showing what the user sent, as they sent it (sent.py)."""

    async def reported(step: str) -> None:
        if message_id := sent.message_id(step):
            step = sent.as_sent(step, await asyncio.to_thread(tasks.message, task_id, message_id))
        await report(step)

    return reported


class _Followed:
    """`report`, counting the progress lines it got, so once the task is stopped the ones written since are read
    from its log (`rest`): the user's messages it passed on just before are among them. A line counts once it's
    reported, so one the stop cut short is reported again."""

    def __init__(self, report: Report) -> None:
        self._report = report
        self._seen = 0

    async def __call__(self, line: str) -> None:
        await self._report(line)
        self._seen += 1

    async def rest(self, tasks: TaskStore, task_id: str) -> None:
        for line in await asyncio.to_thread(tasks.progress_after, task_id, self._seen):
            await self(line)


def _reply(state: TaskState) -> str:
    if state.outcome is not None and state.outcome.ok:
        return state.outcome.text
    if lost(state):
        raise AgentTaskError("The agent's worker ended without a reply: the computer restarted or it was killed.")
    raise AgentTaskError(state.outcome.text if state.outcome else f"The task was {state.status}.")
