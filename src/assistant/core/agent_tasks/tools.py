"""The tools that hand coding tasks to the installed agents and follow them. They're offered only while an
agent plugin is installed, with the agents named in their descriptions, so they come with the MCP tools:
frozen per epoch, and a new epoch when the agents change (core/graph.py). Starting and stopping a task
change the user's code and spend their plan, so the user approves them unless the plugin is trusted."""

from typing import Annotated, Any

from langchain_core.tools import BaseTool, StructuredTool
from langchain_core.utils.function_calling import convert_to_openai_tool
from langgraph.runtime import get_runtime
from pydantic import BaseModel, Field

from assistant.core.agent_tasks.records import TaskState, lost
from assistant.core.agent_tasks.service import MAX_WAIT_SECONDS, AgentTaskError, AgentTasks, FoundTask
from assistant.core.agent_tasks.steps import line
from assistant.core.context import Context
from assistant.core.tools.approval import ask

# Results longer than this are cut in tool output; the whole text stays in the task's result.json.
_MAX_RESULT = 20_000

_START = (
    "Hand a coding task to a coding agent, which works on it on its own in that repository: it reads code, "
    "edits files and runs commands without asking. It runs in the background and survives restarts; this "
    "returns its id at once. It starts with nothing of this conversation, so the task must say everything: "
    "the goal, the files or area, constraints, how to check the work, and what to report. Follow it with "
    "task_status (wait_seconds to wait for it), and continue its work with follow_up_of."
)


class _Start(BaseModel):
    agent: Annotated[str, Field(description="The coding agent, by the name this tool's description lists")]
    repository: Annotated[str, Field(description="Absolute path of the repository or folder to work in")]
    task: Annotated[str, Field(description="The whole brief: goal, constraints, how to check it, what to report")]
    follow_up_of: Annotated[
        str, Field(description="An earlier task's id, to continue its session with what it already knows")
    ] = ""


class _Status(BaseModel):
    task_id: str
    wait_seconds: Annotated[
        int, Field(ge=0, le=MAX_WAIT_SECONDS, description="Wait up to this long for it to finish; 0 answers now")
    ] = 0


class _Stop(BaseModel):
    task_id: str


class _Nothing(BaseModel):
    pass


class AgentTools:
    """The task tools while an agent is installed; none otherwise."""

    def __init__(self, tasks: AgentTasks) -> None:
        self._tasks = tasks
        self._tools: dict[str, BaseTool] = {tool.name: tool for tool in _build(tasks)}

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


def _build(tasks: AgentTasks) -> list[BaseTool]:
    async def start_task(agent: str, repository: str, task: str, follow_up_of: str = "") -> str:
        if rejection := _approve(tasks, agent, f"Start a task in {repository}", task):
            return rejection
        try:
            started = await tasks.start(agent, repository, task, follow_up_of)
        except AgentTaskError as e:
            return str(e)
        return f"Started task {started.id} in {repository}. Follow it with task_status (wait_seconds to wait for it)."

    async def task_status(task_id: str, wait_seconds: int = 0) -> str:
        """A task's state: running, done, failed or stopped, its latest steps, and its result once it ends."""
        try:
            found = await (tasks.wait(task_id, wait_seconds) if wait_seconds else tasks.state(task_id))
        except AgentTaskError as e:
            return str(e)
        return render(found)

    async def list_tasks() -> str:
        """The coding agents' latest tasks, newest first, with their state."""
        return "\n".join(_summary(found) for found in await tasks.recent()) or "No tasks yet."

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
        await tasks.stop(task_id)
        return f"Stopped task {task_id}. Check the repository for what it changed before it stopped."

    return [
        StructuredTool.from_function(coroutine=start_task, description=_START, args_schema=_Start),
        StructuredTool.from_function(coroutine=task_status, args_schema=_Status),
        StructuredTool.from_function(coroutine=list_tasks, args_schema=_Nothing),
        StructuredTool.from_function(coroutine=stop_task, args_schema=_Stop),
    ]


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
