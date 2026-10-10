# Background work

Some work goes on after the call that started it returned: a coding agent's task (`start_task`,
docs/agent-plugins.md), or work an MCP server does after its tool answered (a conversion, a download, a
build). When it ends, the daemon tells the conversation that started it (`core/background.py`):

- The assistant: a note in the turn header of the user's next message in that conversation
  (`core/conversation/ended.py`), once. A scheduled job's conversation gets none: nothing is written there
  again.
- The user: every app shows a notification (the `background_ended` event: `thread_id`, `channel`, `ok`,
  `text`), and when the work was started from a chat channel (Telegram, Slack), the channel gets the same
  text as a message. A channel now on another conversation also hears of it in the turn header of the
  user's next message on it, as with `send_message`.

## Coding agents' tasks

A task started with `start_task` is recorded with the conversation it was started in
(`core/agent_tasks/reports.py`, in the Store). The daemon follows every such task until it ends
(`core/agent_tasks/ends.py`), across restarts, and tells its end: done, failed or stopped, with the start
of its result. When the assistant reads the end itself first (`task_status` on an ended task, or
`stop_task`), nothing is told, and a note already waiting in that conversation is dropped. The end isn't
told while `task_status` is reading the task, so a `task_status` that waits for the end gets it alone.

A conversation handed to an agent (`/claude`) runs its messages as tasks too; their replies come back in
the conversation, so their ends aren't told.

## MCP servers

lo9i advertises the client extension `lo9i/background` in its capabilities. Every call the assistant makes
carries the conversation it's made in, in the request's `_meta`:

```json
{"_meta": {"lo9i/origin": {"user_id": "owner", "thread_id": "…", "channel": "telegram"}}}
```

Treat it as opaque: keep it with the work the call starts, and send it back as it came. A server tells lo9i
about its work with two notifications on its connection, outside the call (the call has returned by
then):

| Method | Params | What |
|---|---|---|
| `notifications/lo9i/work_started` | `work` | Optional. Work named `work` (unique among the server's work in progress, at most 200 characters) is in progress. |
| `notifications/lo9i/work_finished` | `work`, `origin`, `ok`, `text` | It ended. `origin` is the call's `lo9i/origin`; `ok` is `false` when it failed (default `true`); `text` says what came of it, or what went wrong. |

```json
{"jsonrpc": "2.0", "method": "notifications/lo9i/work_finished",
 "params": {"work": "photos", "origin": {"user_id": "owner", "thread_id": "…", "channel": "telegram"},
            "ok": true, "text": "Converted 3 photos to ~/Pictures/converted."}}
```

The end is told like a task's: the user gets `✅ <server>: <text>` (`⚠️` when it failed), and the
assistant a note that names the server, so it reads the text as the server's words. The text is cleaned
like a tool's result and shortened (`core/mcp/background.py`). Notifications whose params don't match are
dropped.

A local server runs on demand and stops after a while without calls (`core/mcp/on_demand.py`), which
would stop its work too. Between `work_started` and `work_finished` it isn't stopped as idle. When the
connection closes (the server crashed, or the daemon stopped), the work it had started no longer holds it.

Local (stdio) servers can always send these notifications. A remote server may have no channel to lo9i
outside a request (the 2026-07-28 protocol over HTTP has none), and then they don't arrive.
