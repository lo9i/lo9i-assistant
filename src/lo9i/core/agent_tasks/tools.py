"""The tools that hand coding tasks to the installed agents and follow them. They're offered only while an
agent plugin is installed, with the agents named in their descriptions, so they come with the MCP tools:
frozen per epoch, and a new epoch when the agents change (core/graph.py). Starting and stopping a task
change the user's code and spend their plan, so the user approves them unless the plugin is trusted. A
task's end is told to the conversation that started it (ends.py), unless these tools showed it first."""

from pathlib import Path
from typing import Annotated, Any, Literal

from langchain_core.messages import ToolMessage
from langchain_core.tools import BaseTool, InjectedToolCallId, StructuredTool
from langchain_core.utils.function_calling import convert_to_openai_tool
from langgraph.config import get_store, get_stream_writer
from langgraph.runtime import get_runtime
from langgraph.store.base import BaseStore
from pydantic import BaseModel, Field

from lo9i.core import inbox, subagent_steps
from lo9i.core.agent_tasks.pending_restart import queue_note, restart_note
from lo9i.core.agent_tasks.records import TaskState, lost
from lo9i.core.agent_tasks.reports import TaskReports
from lo9i.core.agent_tasks.service import MAX_WAIT_SECONDS, AgentTaskError, AgentTasks, CodingAgent, FoundTask
from lo9i.core.agent_tasks.steps import kept_within, line, within_call
from lo9i.core.agent_tasks.waiting import Report
from lo9i.core.background import Origin, current_origin, short
from lo9i.core.config import settings
from lo9i.core.context import Context, require_store
from lo9i.core.conversation import handoffs, queued
from lo9i.core.conversation.handoffs import Handoff
from lo9i.core.conversation.queued import Queued
from lo9i.core.ending import AskedEnding, EndingState
from lo9i.core.subagent_steps import SubagentAnswer
from lo9i.core.tools.approval import ask
from lo9i.core.tools.side import moved_out_of_inbox

# A task's conversation is titled with the start of the task when the call names none.
_TITLE = 60
# Results longer than this are cut in tool output; the whole text stays in the task's result.json.
_MAX_RESULT = 20_000

_START = (
    "Hand a coding task to a coding agent, which works on it on its own in that repository: it reads code, "
    "edits files and runs commands without asking. It runs in the background and survives restarts; this "
    "returns its id at once. It starts with nothing of this conversation, so the task must say everything: "
    "the goal, the files or area, constraints, how to check the work, and what to report. When it ends, the "
    "user is notified and the next message here says so; task_status follows it sooner (wait_seconds to wait "
    "for it). Continue its work with follow_up_of. Where the user is watching, the task goes to the agent as a "
    "conversation instead, so they see its work: in a conversation, it's handed to the agent and the task is its "
    "next message; in the inbox, the task moves to a new conversation handed to the agent. While a restart of "
    "lo9i is pending, a task handed with its conversation would wait for it: by default nothing is handed over and "
    "this says what the restart waits for, so ask the user whether to send it now or after the restart, then call "
    "again with when_restart_pending."
)

RestartChoice = Literal["ask", "send_now", "after_restart"]


class _Start(BaseModel):
    agent: Annotated[str, Field(description="The coding agent, by the name this tool's description lists")]
    title: Annotated[str, Field(description="A few words naming the task, for its conversation")] = ""
    repository: Annotated[str, Field(description="Absolute path of the repository or folder to work in")]
    task: Annotated[str, Field(description="The whole brief: goal, constraints, how to check it, what to report")]
    follow_up_of: Annotated[
        str, Field(description="An earlier task's id, to continue its session with what it already knows")
    ] = ""
    when_restart_pending: Annotated[
        RestartChoice,
        Field(
            description=(
                "Only while a restart of lo9i is pending, for a task handed with this conversation: ask (the "
                "default) hands nothing over and says what the restart waits for; send_now hands it over now and "
                "the restart waits for the task to end; after_restart hands it over with the task once lo9i is back"
            )
        ),
    ] = "ask"


class _Status(BaseModel):
    task_id: str
    tool_call_id: Annotated[str, InjectedToolCallId]
    wait_seconds: Annotated[
        int, Field(ge=0, le=MAX_WAIT_SECONDS, description="Wait up to this long for it to finish; 0 answers now")
    ] = 0


class _Stop(BaseModel):
    task_id: str


class _Nothing(BaseModel):
    pass


class AgentTools:
    """The task tools while an agent is installed; none otherwise."""

    def __init__(self, tasks: AgentTasks, reports: TaskReports, ending: EndingState, store: BaseStore) -> None:
        """`ending`: a restart or stop of lo9i that's pending, which holds back the messages queued in conversations,
        a task handed with its conversation included."""
        self._tasks = tasks
        self._tools: dict[str, BaseTool] = {tool.name: tool for tool in _build(tasks, reports, ending, store)}

    def definitions(self) -> list[dict[str, Any]]:
        if not self._tasks.agents():
            return []
        return [self._definition(tool) for _, tool in sorted(self._tools.items())]

    def tool(self, name: str) -> BaseTool | None:
        return self._tools.get(name) if self._tasks.agents() else None

    def offers(self, name: str) -> bool:
        """It's one of the task tools, whether or not an agent is installed now."""
        return name in self._tools

    def _definition(self, tool: BaseTool) -> dict[str, Any]:
        definition = convert_to_openai_tool(tool)
        if tool.name == "start_task":
            agents = "; ".join(f"{a.server} ({a.name})" for a in self._tasks.agents())
            definition["function"]["description"] = f"{_START} Agents: {agents}."
        return definition


def _build(tasks: AgentTasks, reports: TaskReports, ending: EndingState, store: BaseStore) -> list[BaseTool]:
    async def start_task(
        agent: str,
        repository: str,
        task: str,
        title: str = "",
        follow_up_of: str = "",
        when_restart_pending: RestartChoice = "ask",
    ) -> str:
        found = next((a for a in tasks.agents() if a.server == agent), None)
        handoff = {"command": found.command, "folder": repository, "name": found.name} if found else None
        if handoff and await moved_out_of_inbox(title or short(task, _TITLE), task, handoff):
            return (
                f"Moved this task to a new conversation handed to {handoff['name']} in {repository}, which gets "
                "the task as its first message; the user is taken there. Say so in one short line; don't start it here."
            )
        if found and (where := await _watched_conversation(repository)):
            return await _hand_over(
                tasks, ending, where, found, Path(repository).expanduser(), task, when_restart_pending
            )
        if rejection := _approve(tasks, agent, f"Start a task in {repository}", task):
            return rejection
        try:
            started = await tasks.start(agent, repository, task, follow_up_of)
        except AgentTaskError as e:
            return str(e)
        if (origin := current_origin()) is not None:
            await reports.expect(started.id, origin)
        return f"Started task {started.id} in {repository}. The user is notified when it ends."

    async def task_status(task_id: str, tool_call_id: str, wait_seconds: int = 0) -> str | ToolMessage:
        """A task's state: running, done, failed or stopped, its latest steps, and its result once it ends."""
        shown: list[str] = []
        try:
            async with reports.reading(task_id):
                found = await (
                    tasks.wait(task_id, wait_seconds, _shown_within(tool_call_id, shown))
                    if wait_seconds
                    else tasks.state(task_id)
                )
                if found.state.status != "running":
                    await reports.seen(task_id, current_origin())
        except AgentTaskError as e:
            return str(e)
        return _with_steps(render(found), shown, tool_call_id)

    async def list_tasks() -> str:
        """The coding agents' latest tasks, newest first, with their state; a restart of lo9i that's pending, and the
        messages waiting in the queue, which aren't sent until it's done."""
        listed = "\n".join(_summary(found) for found in await tasks.recent()) or "No tasks yet."
        return "\n\n".join(part for part in [*await _waiting(ending, store), listed] if part)

    async def stop_task(task_id: str) -> str:
        """Stop a running task, and every command it started. What it already changed stays."""
        try:
            found = await tasks.state(task_id)
        except AgentTaskError as e:
            return str(e)
        if found.state.status != "running":
            return f"Task {task_id} isn't running: it's {found.state.status}."
        if rejection := _approve(tasks, found.agent.server, f"Stop task {task_id}", found.state.task.prompt):
            return rejection
        async with reports.reading(task_id):
            await tasks.stop(task_id)
            await reports.seen(task_id, current_origin())
        return f"Stopped task {task_id}. Check the repository for what it changed before it stopped."

    return [
        StructuredTool.from_function(coroutine=start_task, description=_START, args_schema=_Start),
        StructuredTool.from_function(coroutine=task_status, args_schema=_Status),
        StructuredTool.from_function(coroutine=list_tasks, args_schema=_Nothing),
        StructuredTool.from_function(coroutine=stop_task, args_schema=_Stop),
    ]


async def _waiting(ending: EndingState, store: BaseStore) -> list[str]:
    """A restart or stop that's pending and the messages queued meanwhile, for the assistant."""
    origin = current_origin()
    user_id, here = (origin.user_id, origin.thread_id) if origin else (settings.owner_id, "")
    asked = ending.current()
    restart = await restart_note(asked, store, user_id, here) if asked else ""
    return [restart, await queue_note(await queued.waiting(store, user_id), store, user_id, here)]


async def _watched_conversation(repository: str) -> Origin | None:
    """The conversation the user is watching this run in, when the task's folder exists: a task started
    there is handed to its agent with the conversation. None in the inbox (the task moved out of it only
    when it couldn't, which can't happen here), in a scheduled run, or for a folder start_task will refuse."""
    origin = current_origin()
    if origin is None or get_runtime(Context).context.unattended or not Path(repository).expanduser().is_dir():
        return None
    store = require_store(get_store())
    return None if origin.thread_id == await inbox.current(store, origin.user_id) else origin


async def _hand_over(
    tasks: AgentTasks,
    ending: EndingState,
    where: Origin,
    agent: CodingAgent,
    folder: Path,
    task: str,
    when: RestartChoice,
) -> str:
    """From now on the agent answers in this conversation, and its first message there is the task, sent once this
    run ends (core/conversation/queued.py). While a restart is pending, which holds queued messages back, nothing is
    handed over unless the user chose when: now, the restart waiting for the task (core/ending.py), or after it, the
    handoff kept with the task, so neither goes without the other."""
    asked = ending.current()
    if asked is not None and when == "ask":
        return await _restart_question(asked, where, agent.name)
    if rejection := _approve(tasks, agent.server, f"Hand this conversation to {agent.name} in {folder}", task):
        return rejection
    store = require_store(get_store())
    handoff = Handoff(agent.server, agent.command, agent.name, str(folder))
    if asked is not None and when == "after_restart":
        later = Queued(where.channel, task, brief=agent.name, hand_to=handoff)
        await queued.add(store, where.user_id, where.thread_id, later)
        return (
            f"Kept the task for after the {asked.ending}: once lo9i is back, this conversation is handed to "
            f"{agent.name} in {folder} and the task sent to it together. Until then the conversation stays yours. Say "
            "so in one short line; don't call start_task again."
        )
    await handoffs.hand(store, where.user_id, where.thread_id, handoff)
    await queued.add(store, where.user_id, where.thread_id, Queued(where.channel, task, brief=agent.name))
    # Should a restart be asked for before it's sent, it waits for this task all the same.
    ending.send_first(where.thread_id)
    waits = f" The pending {asked.ending} waits until the task ends." if asked else ""
    return (
        f"This conversation is now handed to {agent.name} in {folder}, which gets the task as soon as this reply "
        f"ends; the user sees its work here.{waits} Say so in one short line; don't call start_task again."
    )


async def _restart_question(asked: AskedEnding, where: Origin, agent: str) -> str:
    """Nothing was handed over: what the assistant tells the user, and how to go on once they choose."""
    store = require_store(get_store())
    note = await restart_note(asked, store, where.user_id, where.thread_id)
    return (
        f"{note}\n\nNothing was handed over and the task wasn't queued: it would wait for the {asked.ending}, "
        f"and {agent} would get nothing meanwhile. Tell the user and ask which they want: send it now (the "
        f"{asked.ending} waits until the task ends), or after the {asked.ending} (the conversation is handed to "
        f"{agent} with the task once lo9i is back). Then call start_task again with the same arguments and "
        'when_restart_pending set to "send_now" or "after_restart".'
    )


def _shown_within(call_id: str, shown: list[str]) -> Report:
    """While task_status waits, the apps show the task's steps inside its call; each is noted in `shown`."""
    write = get_stream_writer()

    async def _report(message: str) -> None:
        shown.append(message)
        for event in within_call(message, call_id):
            write(event)

    return _report


def _with_steps(text: str, shown: list[str], call_id: str) -> str | ToolMessage:
    """The result, with the steps shown inside the call kept beside it, so history shows them again."""
    if not (steps := kept_within(shown)):
        return text
    return subagent_steps.result(SubagentAnswer(text, steps), call_id, "task_status")


def _approve(tasks: AgentTasks, agent: str, action: str, brief: str) -> str | None:
    """None when the plugin is trusted or the user approves; otherwise why not, for the model."""
    if tasks.trusted(agent):
        return None
    request = {"tool": agent, "command": f"{action}:\n\n{brief}", "reason": f"{agent} edits files and runs commands"}
    return ask(request, get_runtime(Context).context)


def render(found: FoundTask) -> str:
    task = found.state.task
    lines = [_summary(found), f"Repository: {task.repository}", f"Asked: {_short(task.prompt, 500)}"]
    if task.follow_up_of:
        lines.append(f"Follows up on: {task.follow_up_of}")
    if steps := [text for step in found.state.progress if (text := line(step))]:
        lines += ["", "Latest steps:", *(f"- {text}" for text in steps)]
    lines += ["", *_ending(found.state)]
    return "\n".join(lines).rstrip()


def _ending(state: TaskState) -> list[str]:
    outcome = state.outcome
    if lost(state):
        return ["Its worker ended without a result: the computer restarted or the process was killed."]
    if outcome is None:
        return [] if state.status == "stopped" else ["Still working."]
    cost = [f"Cost: ${outcome.cost_usd:.2f}"] if outcome.cost_usd is not None else []
    follow = f'To continue this work, call start_task with follow_up_of="{state.task.id}".'
    return ["Result:" if outcome.ok else "Failed:", _short(outcome.text, _MAX_RESULT), *cost, "", follow]


def _summary(found: FoundTask) -> str:
    task, status = found.state.task, found.state.status
    where = f"started {task.started_at}, in {task.repository}"
    return f"{task.id} ({found.agent.name}): {status}, {where}: {_short(task.prompt, 80)}"


def _short(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit] + " […]"
