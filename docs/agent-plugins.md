# Agent plugins

A coding agent (Claude Code, GitHub Copilot) is a plugin installed from the extras repository. The
daemon does everything that is the assistant's (`core/agent_tasks/`): it gives the assistant the task
tools (`start_task`, `task_status`, `list_tasks`, `stop_task`) while an agent plugin is installed, asks
the user before a task starts or stops unless the plugin is trusted, keeps each task's records, follows
them, and runs a conversation handed to the agent (`/claude <folder>`) one task per message. The plugin
only brings a worker: a command that runs one task with its agent. It needs no code from lo9i.

## server.yaml

```yaml
name: claude-code
version: 2.0.0
# 3 for an agent's worker (core/repositories/formats.py).
format: 3
description: Hand coding tasks to Claude Code
fields:
  - {key: CLAUDE_TOKEN, label: Claude token or Anthropic API key, secret: true, optional: true}
# Optional: lo9i's Copilot login as LO9I_COPILOT_GITHUB_TOKEN (core/mcp/logins.py).
model_login: copilot
trusted: false
agent:
  # The apps' command that hands a conversation to it: /claude <folder>, /claude off.
  command: claude
  name: Claude Code
  # Run for each task, with the task's folder as its last argument.
  worker: "{bin}/claude-code-worker"
  args: []
```

The worker runs with the plugin's env and field values, its login, `TZ`, and `LO9I_UPLOADS`, in the plugin's
folder. `LO9I_UPLOADS` is the folder where the files the user sends the agent are saved: a message names them
by their full paths there, outside the repository, so an agent that only opens files in its folder must be let
into it (Copilot's `--add-dir`).
`{dir}`, `{data}`, `{bin}`, `{uv}`, `{python}` work in `worker` and `args` as in an MCP command.

## The task folder

Each task is a folder under the plugin's data folder, `tasks/<id>/`. Every file has one writer.

| File | Writer | What |
|---|---|---|
| `task.json` | daemon | `{"id", "repository", "prompt", "session", "follow_up_of", "started_at"}`. `repository` is where to work. `session` is the agent's session id: a new uuid, or the session of the task in `follow_up_of`, which the worker continues. |
| `pid` | worker | Its process id, written first. |
| `progress.log` | worker | One step per line, as JSON (below), appended as the agent works. |
| `result.json` | worker | `{"ok", "text", "finished_at", "cost_usd"}`, written last, whole (write it to another name, then rename). `text` is the agent's final answer, or what went wrong. |
| `context.json` | worker, optional | `{"tokens", "window"}`: how full the agent's context is, `tokens` of the model's `window`, written whole (to another name, then renamed) as the agent works, as often as it's cheap to learn (after a step, at most every few seconds), and once more just before `result.json`. While a conversation is handed to the agent, the apps show it as the conversation's context, from the latest task in its session that wrote one (the one running included), and follow each new one (an `agent_context` event). A separate file because a daemon from before it reads `result.json` into its own fields only. |
| `stopped` | daemon | The user stopped the task. |
| `sent_on` | daemon | The messages the task ended without taking went to the agent next (below), so they go only once. |
| `conversation` | daemon | The conversation handed to the agent that the task answers in. The worker doesn't read it. |
| `inbox/` | worker makes it, daemon writes in it | What the user sends the task while it works (below). |
| `worker.log` | the worker's output | For finding out why a worker failed. |

The daemon starts the worker detached, so it outlives a restart of the daemon. Stopping a task signals
the worker's process group with SIGTERM, so the worker makes itself the leader of its own (`setsid`) and
everything it starts stops with it. A worker that finds `stopped` when it starts ends at once. A task
whose worker is gone without a `result.json` counts as failed.

When a task started with `start_task` ends, the daemon tells the conversation that started it and the
user, unless the assistant read its end first (docs/background-work.md).

## Messages while it works

In a conversation handed to the agent, the user can write to it while it works on a message, and
interrupt it (`POST /conversations/<id>/agent/messages`, `/agent/interrupt`; `AgentTasks.message`,
`interrupt`). A worker that takes them makes `inbox/` once it's ready, after handling SIGUSR1: the
daemon sends nothing to a task without one, and the apps say the agent can't take messages while it
works. The daemon writes each message as a JSON file in `inbox/`, written whole and then renamed, named so
the files sort in the order they were sent, and then sends SIGUSR1 to the worker's pid only (the commands
it started would end on it).

| Message | What the worker does |
|---|---|
| `{"kind": "message", "text"}` | Passes it on to the agent, which takes it between its steps, and writes a `user` step with the file's name (without `.json`) as its `id`. The daemon also writes `said` and `files` (what the user wrote and the files they sent, which `text` names with where they're saved): they're its own, for showing the step as the user sent it (`core/agent_tasks/sent.py`); a worker leaves them alone. |
| `{"kind": "interrupt"}` | Stops the agent's step in progress; the task stays running and waits for the next message. |

An agent that gets to a message only later (Claude Code takes what it's sent once it's done with the turn in
progress) marks its `user` step `"waiting": true`, and writes a `taken` step with the message's id once the
agent gets to it. A `user` step without `waiting` counts as taken. The apps show a waiting message as waiting
until its `taken` step.

The task ends once the agent has answered every message it was sent. Messages left in `inbox/` without a
`user` step when it ends (sent just as it finished) go to the agent next, as a follow-up in the same
session, in the same run. When the user stops the run, or the task fails, the messages the agent hadn't taken
(left in `inbox/` without a `user` step, or with a `waiting` one and no `taken` step) go to it next, together as
one message following up the task in its session, as a run of their own once that one ends
(`core/conversation/queued.py`); the conversation stays handed to the agent. The apps show them as not taken in
the run that ended and that message as them sent again (`core/conversation/resent.py`), not as new ones.

## Steps

Each line of `progress.log` is a JSON object with a `kind`; fields that are empty may be left out.

| Kind | Fields | What |
|---|---|---|
| `note` | `text` | A line about the task itself ("Downloading the CLI"). A line that isn't JSON counts as a note. |
| `text` | `text` | What the agent says between its tool calls. |
| `thinking` | `text` | The agent's reasoning, when its model shows it. |
| `tool` | `tool`, `detail`, `id` | A tool call starting: its name, what it's about (a command, a file), its id. |
| `result` | `tool`, `text`, `id` | A tool call's result: the call it ends, its output, shortened. |
| `text_delta` | `text` | Words of a text as they're written. The whole text follows as a `text` step. |
| `thinking_delta` | `text` | Words of a thinking as they're written. The whole thinking follows as a `thinking` step. |
| `user` | `text`, `id`, `waiting` | A message the user sent while it worked, passed on to the agent; `id` is its file in `inbox/`. `waiting`: the agent gets to it only later (above). |
| `taken` | `id` | The agent got to a message whose `user` step was `waiting`: it no longer shows as waiting. |

`within` on any step is the id of the tool call whose subagent took it. In a conversation handed to the
agent, the daemon shows text as the reply, thinking apart, and each tool call with its result
(`core/agent_tasks/steps.py`); notes go inside a call named after the agent, and `user` steps show as the
user's messages (a `UserSaid` event). Words stream as they're
written, and the whole text or thinking that follows them isn't shown again; a worker that writes no
deltas shows each block whole. History and the task tools keep only the whole blocks. The daemon reads
new lines at most a tenth of a second after they're written. The task tools show notes, text and tool
calls as the task's latest steps.
