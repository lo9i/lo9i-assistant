# Channel plugins

A channel (Telegram, Slack) is a plugin installed from the extras repository. The daemon runs its
process and the process talks to the daemon over HTTP, like the apps do, but with a token that only
reaches its own channel routes.

The daemon does everything that is the assistant's: it decides which conversation each message goes to,
runs it, shows each run as chat messages (a status message for tool calls, the reply streamed by edits and
split to fit, its first message tagged with the conversation, `[watchlist] …`), writes the approval and
question messages and their buttons, and decides what a pressed button does (`core/channels/chat/`). The process only connects to its chat service: it sends the daemon what
the user does there (a message, a button pressed, a command) and carries out the chat operations the
daemon sends back (send, edit, typing, voice). It needs no code from lo9i.

## server.yaml

```yaml
name: telegram
version: 1.0.0
# The plugin format (core/repositories/formats.py): 2 for {bin}.
format: 2
description: Chat with the assistant on Telegram
# Only for a plugin outside a category's folder: in the extras it lives in communications/chat/,
# which gives its category (core/repositories/categories.py). A channel is always in
# communications/chat, which is also what it gets without this line.
category: communications/chat
fields:
  - {key: TELEGRAM_TOKEN, label: Bot token, secret: true, help: https://t.me/BotFather}
channel:
  command: "{bin}/lo9i-telegram"
  # The version of this protocol the process speaks. The daemon doesn't run a channel for another
  # version, and the apps tell the user to update the plugin or lo9i; 1 when absent.
  protocol: 2
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
| `GET /stream` | Server-Sent Events, kept open while the process runs. Each event has an `event:` kind and JSON `data:`. The query gives the channel's limits: `edit_seconds` (the least time between two edits of a message, 1.0 by default), `draft_limit` (a reply is shown as drafts while it's at most this long, 3500), `message_limit` (the longest message; longer replies are split, 3500) and `voice` (it sends voice notes, `false`). While it's open the channel takes chat operations, `send_message` messages and job approvals. A second stream replaces the first. |
| `PUT /status` | `{"items": [SetupItem, ...]}`: what the apps show for this channel (see below). Send it after connecting and whenever it changes. |
| `POST /deliveries/{id}` | `{"error": "", "message": ""}`: an operation's result. `error` is empty when it was carried out, otherwise why not; `message` is the id of the message a `send` sent. Unanswered within 30 seconds counts as failed. |
| `POST /messages` | Multipart form: `chat` (the chat's id in the service), `text`, `voice` (`true` for a voice note: Settings → Audio can speak only those replies), `files` (repeated), and optionally `reply_to` (the id of the message it replies to) and `message` (its own id). A reply goes on in the conversation of the message it replies to; any other message goes to the inbox, which routes it to the conversation it's about or a new one (after `/new`: a new one). Send `message` so replying to the user's own message works too. What follows comes as operations for that chat. |
| `POST /presses` | `{"chat": "...", "message": "...", "text": "...", "data": "..."}`: a button pressed. `message` is the id of the message it's on and `text` that message's text, which the daemon shows again without the buttons; `data` is the button's data, as the daemon gave it. |
| `POST /commands` | `{"command": "new", "text": ""}`: a command without its slash, and what follows it. `new` sends the next message to a new conversation, `start` greets, and an agent's command hands the conversation the channel last wrote in to it (a new one when that was the inbox; `claude` with a folder in `text`, or `off` to take it back), and the channel's messages go on there until it's taken back. Returns `{"text": "..."}`, what to answer. Send every command the user types: the daemon knows which exist. |

`POST /messages` and `POST /presses` answer at once; the run goes on in the daemon, where the apps see
it too.

### Stream events

| Kind | Data | What the channel does |
|---|---|---|
| `hello` | `{"assistant_name": "...", "commands": [{"command", "description"}, ...]}` | First event of every stream. `commands` are what the channel offers its user, without the slash: `new` and each installed agent's (Telegram's command menu, Slack's manifest). |
| `commands` | `{"commands": [...]}` | The commands changed: an agent plugin was installed or removed. |
| `renamed` | `{"assistant_name": "..."}` | The assistant was renamed (Telegram renames its bot). |
| `action` | `{"action": "..."}` | The user pressed a setup button in an app (a SetupItem of kind `action`). |
| `send` | `{"id", "chat", "text", "markdown", "buttons"}` | Send `text` (Markdown when `markdown` is true) with `buttons`, `[[label, data], ...]`, then `POST /deliveries/{id}` with the new message's id. |
| `edit` | `{"id", "chat", "message", "text", "markdown", "buttons"}` | Replace message `message`'s text and buttons; no buttons removes them. |
| `typing` | `{"id", "chat"}` | Show that the assistant is writing, where the service can; otherwise just confirm. |
| `voice` | `{"id", "chat", "audio"}` | Send `audio`, OGG Opus in base64, as a voice note. Only sent when the stream said `voice=true`. |

An operation's `chat` is the id the channel gave in `POST /messages` or `POST /presses`. An empty
`chat` is the user's own chat on the channel, for what the assistant starts (`send_message`, the end of
background work, a scheduled job's approval): every paired Telegram account, the owner's Slack DM. The id a
`send` there confirms is kept with the conversation that sent it, and a reply naming it in any chat
(`reply_to`) goes on there; when it went to several paired Telegram accounts, return the last one's. Run each operation as
it comes and confirm it with its result; the daemon waits for one before sending the next of a turn.

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
