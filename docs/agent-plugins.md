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

The worker runs with the plugin's env and field values, its login, and `TZ`, in the plugin's folder.
`{dir}`, `{data}`, `{bin}`, `{uv}`, `{python}` work in `worker` and `args` as in an MCP command.

## The task folder

Each task is a folder under the plugin's data folder, `tasks/<id>/`. Every file has one writer.

| File | Writer | What |
|---|---|---|
| `task.json` | daemon | `{"id", "repository", "prompt", "session", "follow_up_of", "started_at"}`. `repository` is where to work. `session` is the agent's session id: a new uuid, or the session of the task in `follow_up_of`, which the worker continues. |
| `pid` | worker | Its process id, written first. |
| `progress.log` | worker | One step per line, as JSON (below), appended as the agent works. |
| `result.json` | worker | `{"ok", "text", "finished_at", "cost_usd"}`, written last, whole (write it to another name, then rename). `text` is the agent's final answer, or what went wrong. |
| `stopped` | daemon | The user stopped the task. |
| `worker.log` | the worker's output | For finding out why a worker failed. |

The daemon starts the worker detached, so it outlives a restart of the daemon. Stopping a task signals
the worker's process group with SIGTERM, so the worker makes itself the leader of its own (`setsid`) and
everything it starts stops with it. A worker that finds `stopped` when it starts ends at once. A task
whose worker is gone without a `result.json` counts as failed.

When a task started with `start_task` ends, the daemon tells the conversation that started it and the
user, unless the assistant read its end first (docs/background-work.md).

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

`within` on any step is the id of the tool call whose subagent took it. In a conversation handed to the
agent, the daemon shows text as the reply, thinking apart, and each tool call with its result
(`core/agent_tasks/steps.py`); notes go inside a call named after the agent. Words stream as they're
written, and the whole text or thinking that follows them isn't shown again; a worker that writes no
deltas shows each block whole. History and the task tools keep only the whole blocks. The daemon reads
new lines at most a tenth of a second after they're written. The task tools show notes, text and tool
calls as the task's latest steps.
