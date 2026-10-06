# Backlog

Open work, tackled one at a time. Finished items are deleted and the remaining codes renumbered.
A = action, G = memory gap, H = context improvement, Q = open question, R = risk.

## Agent

- A13. Named subagents (a researcher, a coder) as plugins from the extras with an `agent:` section in server.yaml: their own prompt, tools and model.
- A14. Subagents in scheduled jobs. Approvals inside a delegated task follow the job's forwarding rules (`core/approvals.py`).
- A15. Subagent steps in Telegram and Slack: `lib/lo9i-chat` in the extras doesn't know `within` on tool events yet, so a subagent's calls show there as the agent's own. Show them under the delegate call, or not at all.
- A16. A subagent's steps aren't kept: after a reload, or in a conversation opened later, a delegate call shows only its task and answer. Its checkpoint is in the conversation's thread under the call's namespace; the history the apps load could include them.
- A17. An approval waiting in home blocks every channel there: a message from Telegram while the web app's approval is open only repeats the approval (`core/agent/runs.py`). Show it on the channel with its buttons so it can be answered there, or let the message through and answer the approval as rejected.
- A18. Pinning skills from Telegram and Slack. The web and terminal apps pin with `/pin` and `/unpin` (`core/conversation/pinned.py`); a channel's token reaches only `/channels/<name>/...`, so the channel protocol needs pin routes and `lib/lo9i-chat` in the extras the commands.

- A22. A conversation handed to an agent (/claude) shows nothing while the agent works, which can take minutes: only its reply when it's done. Stream its steps (the task's progress lines, through MCP progress notifications) as they happen, like a delegate call's.
- A23. Telegram and Slack can't hand a conversation to an agent: their commands are fixed in `lib/lo9i-chat`. Offer the agents' commands there too, with the folder typed after the command.
- A24. Files a subagent's tools bring (an email's attachments read inside `delegate`) sit in its checkpoint under the call's namespace, which the Files list (`core/agent/files.py`) and deleting a conversation (`core/agent/threads.py::_delete_files`) don't read: they aren't listed, and stay on disk after the conversation is deleted. Read the delegate calls' namespaces too.
- A25. The GitHub Copilot agent (`assistant/agents/copilot` in the extras, /copilot) isn't told not to stop lo9i's daemon, as Claude Code is (`_UNDER_LO9I` in its runner.py): stopping the daemon during a handed-off conversation stops it before it replies. Its CLI takes only `--prompt`; find how it takes extra instructions and give it the same note, with `/system/restart` as the way to restart.

## Daemon

- A1. Restart or stop the daemon from the app.
- A2. Network access, follow-ups. HTTPS and device pairing are done (`daemon/auth.py`, `daemon/https.py`); left:
  - Passkeys as a faster sign-in for paired devices.
  - Bearer tokens for non-browser clients on other hosts (the terminal app over the network). The daemon already accepts `Authorization: Bearer`; no client sends one yet.
- A3. Scheduled jobs only run while the host is up. If the Linux host is a machine that suspends (a laptop), keep it awake on power or schedule wake-ups (`rtcwake`), so jobs run on time.
- A4. Spending limits on the token ledger (`core/usage`): per job run, per job per day, per conversation and overall per day. Checked before every model call; going over ends the run cleanly (a job run is recorded as over budget, a chat gets a clear message), and a warning at a threshold (80%) goes to Telegram or Slack.

## MCP

- A7. Requests from MCP servers: elicitation (a form for the user, through the approval surface on every channel) and sampling (the server asks the model for text; rate-limited, with a token cap). Both are refused today.
- A8. MCP resources and prompts: per-server `list_resources`, `read_resource`, `list_prompts`, `get_prompt` tools, added only when the server supports them and the user turns them on.
- A9. MCP startup: start a server on its first call from a cached tool list (for servers that use a lot of memory), and limit how many connect at once when the daemon starts.
- A12. Signing in to a remote MCP server whose authorization server has no dynamic client registration: today the sign-in fails at registration (`core/mcp/oauth.py`). The Sign in dialog takes a client ID and secret of the user's own OAuth app, saved as the server's registered client so registration is skipped, and shows the redirect URI to register with it, as email does. A client metadata URL (the spec's other option) doesn't fit: the authorization server must fetch it, and the daemon is reachable only on the tailnet.

## Plugins

- A19. A plugin can't tell lo9i that background work finished. The coding agents' tasks (`assistant/agents/claude-code`, `copilot` in the extras) run for minutes; the agent learns the result only by calling `task_status`, and the user isn't told when one ends. Let an MCP server send an event (a notification on its connection) that lo9i delivers to the conversation that started the task, as a turn header note or a message on its channel.
- A20. A plugin's token is checked only when it's first used: a wrong Claude key fails the first coding task after about three minutes of Claude Code's retries. Let a plugin declare a check that runs when its fields are saved (a command or a tool), and show its error in the install dialog.
- A21. Calls (the phone plugin) and anything else that opens an app need lo9i in the user's login session: from boot (`/startup`, a LaunchDaemon) `open` has no screen. Run the daemon as a LaunchAgent in the user's session on macOS, or keep a helper there for what needs the screen.

## Context

- H1. Better epoch summaries: quote user messages verbatim, keep ids and paths exactly, and let `search_memory` search tool outputs too (it covers only what the user and the assistant wrote).
- H2. Old tool results are trimmed after a fixed `prompt_cache_minutes` (5) idle gap (`core/conversation/trim.py`), the same for every provider. A provider whose cache lasts longer (Anthropic's 1-hour cache, some OpenAI models) loses a cache that was still valid. Take the cache lifetime from the model choice (`core/llm/providers.py`) instead of one setting; a local model with no cache could trim at any user message.

## Voice

- A5. Real-time voice agent: live spoken conversation from the browser.
  - A speech-to-speech model (OpenAI GPT-Live) listens and speaks. No separate speech-to-text or text-to-speech step; transcripts come from the model's own events.
  - Audio goes directly between the browser and OpenAI over WebRTC. The daemon only exchanges the connection offer and answer, and never handles audio.
  - The daemon keeps a sideband WebSocket to OpenAI for each call. When the voice model needs to act, it calls a tool; the daemon runs it through `AssistantService`, so Claude stays the brain.
  - Tool calls are logged by the model's call id, so a retried call returns the first result.
  - Needs an OpenAI key in addition to the Anthropic key. Not needed for Telegram voice notes.
- A6. Spoken replies in Slack. Settings → Audio speaks replies in the web chat and as Telegram voice notes; Slack doesn't get them yet (upload the audio with `files.uploadV2`).


## Platforms

- A10. Windows. Nothing runs there today: the terminal app reaches the daemon only through a Unix socket (`client/connection.py`), and `/startup` knows only launchd and systemd (`daemon/startup.py`).
  - Daemon connection: a named pipe or localhost with a paired device instead of the Unix socket.
  - Startup: a Task Scheduler task or a Windows service as a `daemon/startup.py` backend.
  - Clipboard: `client/clipboard/windows.py`, pasting files, images and text with PowerShell (`Get-Clipboard -Format FileDropList`, `System.Windows.Forms.Clipboard.GetImage`) and copying with `Set-Clipboard`.
  - Bash tool, data paths and `install.sh`: decide between native Windows and running under WSL.

## Languages

- A11. Multi-language support. The app's own text is English only.
  - Interface text: terminal app, web app, and the messages Telegram and Slack adapters send (approval buttons, errors, `/new`). Text kept in per-language files, picked in Settings → General.
  - Prompts in `core/conversation/prompts/` stay in English; the model replies in the user's language.
  - Speech: the speech-to-text language and the Kokoro voice follow the chosen language.
  - Dates and times in the apps use the language's format.

## Open questions and risks

- R1. Bash runs on the host as the daemon's user. It can read `~/.lo9i` (including the database with the Telegram token, the email password and MCP servers' keys) and that user's other files. Only dangerous-command approvals stand in the way. With remote access (A2), a stolen paired device can reach this too until it's revoked. A paired device can also add a local MCP server, which runs its command without approval. Options: run the daemon as a dedicated user with little else on the host, and run just the bash tool in a sandbox container.
- R2. MCP servers send text the model reads (tool descriptions and results). Hidden Unicode tag characters are stripped and write tools on untrusted servers need approval, but visible injected instructions still reach the model. A server whose tool list keeps changing starts a new epoch at each message (a prompt cache miss each time).
- Langfuse: run the self-hosted stack and set keys.
