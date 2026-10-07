# Channel plugins

A channel (Telegram, Slack) is a plugin installed from the extras repository. The daemon runs its
process and the process talks to the daemon over HTTP, like the apps do, but with a token that only
reaches its own channel routes.

## server.yaml

```yaml
name: telegram
version: 1.0.0
# The plugin format (core/repositories/formats.py): 2 for {bin}.
format: 2
description: Chat with the assistant on Telegram
# Folders under lib/ in the repository that the plugin uses. They're installed next to the plugins'
# folders, so a uv path dependency on ../../lib/<name> works both in the repository and once installed.
libraries: [lo9i-chat]
# Only for a plugin outside a category's folder: in the extras it lives in communications/chat/,
# which gives its category (core/repositories/categories.py). A channel is always in
# communications/chat, which is also what it gets without this line.
category: communications/chat
fields:
  - {key: TELEGRAM_TOKEN, label: Bot token, secret: true, help: https://t.me/BotFather}
channel:
  command: "{bin}/lo9i-telegram"
  # How to write for this channel; it goes in the system prompt's Channels section.
  style: A phone chat. Short messages. Simple Markdown only (bold, italics, code); no tables or headings.
```

A plugin may also have `command`/`args` (an MCP server, as before): the Slack plugin has both. The
fields' values and `env` go to both processes. `{dir}`, `{data}`, `{bin}`, `{uv}`, `{python}` work in
`channel.command` and `channel.args` as in the MCP command.

## The process

The daemon starts `channel.command` while the plugin is enabled, restarts it when it exits (waiting
longer each time), and stops it when the plugin is turned off or removed. Its output goes to the
daemon's log. Its environment has the server's env plus:

- `LO9I_URL`: the daemon, `http://127.0.0.1:<port>`
- `LO9I_CHANNEL`: the plugin's name
- `LO9I_CHANNEL_TOKEN`: a token for this run of the process
- `TZ`: the assistant's time zone (`TIMEZONE`), as for local MCP servers

Every request carries `Authorization: Bearer $LO9I_CHANNEL_TOKEN` and `X-Lo9i-Client: channel`. The
token reaches only `/channels/<its name>/...`; anything else answers 403.

## Routes, under /channels/{name}

| Route | What |
|---|---|
| `GET /stream` | Server-Sent Events, kept open while the process runs. Each event has an `event:` kind and JSON `data:`. While it's open the channel can deliver `send_message` messages and job approvals. A second stream replaces the first. |
| `PUT /status` | `{"items": [SetupItem, ...]}`: what the apps show for this channel (see below). Send it after connecting and whenever it changes. |
| `POST /deliveries/{id}` | `{"error": ""}`: the result of a `deliver` or `approval` event. Empty error means delivered. Unanswered within 30 seconds counts as failed. |
| `POST /conversation` | Start a side conversation (the channel's `/new`). Returns `{"thread_id": "..."}`. |
| `DELETE /conversation` | Go back to the home conversation (the channel's `/home`). Returns `{"thread_id": "..."}`. A channel is on home until its `/new`. |
| `POST /messages` | Multipart form: `text`, and `files` (repeated). Sends a user message in the channel's current conversation. Returns `{"run_id": "..."}`. |
| `POST /approvals` | `{"decisions": {"<interrupt_id>": {"approved": true, "reason": ""}}}`, a question's `{"choices": [...]}` (`null` when skipped), or a side conversation suggestion's `{"moved": bool}`. Resumes the channel's conversation. Returns `{"run_id": "..."}`. On `moved: true`, once that run ends, start a side conversation (`POST /conversation`) and send the request's `first_message` there. |
| `GET /approvals` | The approvals and questions the channel's conversation waits for: `[{"interrupt_id": "...", "request": {...}}]`. |
| `GET /runs/{run_id}/events` | A run's events as Server-Sent Events: `data:` is an event (`{"type": "TextDelta", ...}`, the same JSON as `/runs/{id}/events`), each with an `id:`; the last one has `event: end`. Send `Last-Event-ID` to resume. |
| `POST /job-approvals/{interrupt_id}` | `{"approved": true, "reason": ""}`: the answer to an `approval` event. Returns `{"waiting": bool}`: false when the job's run already went on without it. |
| `POST /speech` | `{"text": "...", "after_voice_message": bool}`: the reply as OGG Opus voice (`audio/ogg`) when Settings → Audio says replies are spoken in this case, else 204. 400 with `detail` when speech fails. |

### Stream events

| Kind | Data | What the channel does |
|---|---|---|
| `hello` | `{"assistant_name": "..."}` | First event of every stream. |
| `renamed` | `{"assistant_name": "..."}` | The assistant was renamed (Telegram renames its bot). |
| `deliver` | `{"id": "...", "text": "..."}` | Send `text` to the user, then `POST /deliveries/{id}`. |
| `approval` | `{"id": "...", "interrupt_id": "...", "title": "...", "request": {...}}` | A scheduled job's run asks for approval: show it with Approve and Reject buttons (`ja:`/`jr:`, `gateways/chat/approvals.py`), then `POST /deliveries/{id}`. A press answers with `POST /job-approvals/{interrupt_id}`. |
| `action` | `{"action": "..."}` | The user pressed a setup button in an app (a SetupItem of kind `action`). |

### SetupItem

`{"kind": "text" | "code" | "copy" | "action", "label": "...", "value": "..."}`

`label` names the item and `value` holds it.

- `text`: a line, shown as `label: value`, or just `value` when `label` is empty, such as `Bot: @name` or an error.
- `code`: a short value to read out, such as a pairing code.
- `copy`: a longer value the user copies, such as Slack's app manifest.
- `action`: a button labelled `label`; `value` is the action id sent back in an `action` event.

## Apps

`GET /channels` lists the installed channel plugins for the apps: name, description, whether its
process is connected, and its items. `POST /channels/{name}/actions/{action}` presses an action.
These two are for paired devices and the Unix socket, not channel tokens. The apps show a channel's
items in its plugin's details in Plugins.
