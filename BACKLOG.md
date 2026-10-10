# Backlog

Open work, tackled one at a time. Finished items are deleted and the remaining codes renumbered.
A = action, G = memory gap, H = context improvement, Q = open question, R = risk.

## Agent

- A13. Named subagents (a researcher, a coder) as plugins from the extras with an `agent:` section in server.yaml: their own prompt, tools and model.
- A14. Subagents in scheduled jobs. Approvals inside a delegated task follow the job's forwarding rules (`core/approvals.py`).
- A16. A subagent's steps aren't kept: after a reload, or in a conversation opened later, a delegate call shows only its task and answer. Its checkpoint is in the conversation's thread under the call's namespace; the history the apps load could include them.
- A17. An approval waiting in home blocks every channel there: a message from Telegram while the web app's approval is open only repeats the approval (`core/agent/runs.py`). Show it on the channel with its buttons so it can be answered there, or let the message through and answer the approval as rejected.
- A18. Pinning skills from Telegram and Slack. The web and terminal apps pin with `/pin` and `/unpin` (`core/conversation/pinned.py`); channels' commands go to `POST /channels/<name>/commands` (`core/channels/chat/conversations.py`), which needs `pin` and `unpin`, and each plugin has to register them with its service (Telegram's command list, Slack's manifest).

- A21. Files a subagent's tools bring (an email's attachments read inside `delegate`) sit in its checkpoint under the call's namespace, which the Files list (`core/agent/files.py`) and deleting a conversation (`core/agent/threads.py::_delete_files`) don't read: they aren't listed, and stay on disk after the conversation is deleted. Read the delegate calls' namespaces too.
- A23. The /claude folder picker (`core/conversation/agent_folders.py`) leaves out hidden folders, so a project under a dot folder can only be typed as a path. The plain REPL (pipes) offers only the workspace and the folders used before, with no browsing. Add a way to show hidden folders, and browsing in the REPL if it's needed there.
- A24. The web app's folder picker (`clients/web/src/lib/ui/chat/AgentFolderModal.svelte`) has no component test, unlike `ApprovalModal`. Cover picking a recent folder and browsing to a new one.
- A26. Files sent to a handed-off agent reach it as full paths under `~/.lo9i/uploads`, outside the folder it works in. Claude Code reads them (`bypassPermissions`); the Copilot CLI may refuse paths outside its folder with only `--allow-all-tools`. Check it on a computer with Copilot and pass the uploads folder (`--add-dir`) if needed.
- A22. A channel's turn stops showing in its chat when the channel's stream drops mid-turn (its process restarts after a plugin update): each chat operation fails at once while it's away (`core/channels/hub.py::operate`), and `ChannelChats` gives up on the turn. The run goes on and the apps show it. Wait for the channel to reconnect for a while, or show the rest of the reply once it's back.
- A29. A handed-off agent's subagent steps aren't kept: live, the steps Claude Code's own subagents take show inside the call that started them, but history (`core/conversation/display.py::_agent_reply`) leaves out steps with `within`. Show them under their call there too.
- A31. A conversation whose titling fails (the worker model unreachable) stays untagged until it's left again or the daemon restarts: `title_untitled` (`core/agent/conversations.py`) runs once at start. On 2026-10-09 one title call at start hung for hours past the 600s read timeout (`core/llm/copilot.py`), holding up the whole pass. Find why that call didn't time out, and tag conversations that are missing tags when the worker model answers again.
- A32. When background work ends (`core/background.py`), the assistant hears of it only in the turn header of the user's next message in that conversation, and the user gets a notification with the start of the result. Let the assistant follow up on its own when the result needs explaining (a run in that conversation), and let the apps' notification open the conversation.
- A33. The `background_ended` notification reaches the apps only while one is open: work started from the web or terminal app while none is open is told only in the next turn header there. Keep the ends listed in the apps (like Alerts), or send them to a chat channel too.
- A35. The steps a task shows inside a waiting `task_status` call (`core/agent_tasks/steps.py::within_call`) aren't kept: after a reload the call shows only its result. Keep them with the call's result, the way a handed-off reply keeps its steps (`response_metadata`), and show them in history (`core/conversation/display.py`).

## Daemon

- A1. Restart or stop the daemon from the app.
- A2. Network access, follow-ups. HTTPS and device pairing are done (`daemon/auth.py`, `daemon/https.py`); left:
  - Passkeys as a faster sign-in for paired devices.
  - Bearer tokens for non-browser clients on other hosts (the terminal app over the network). The daemon already accepts `Authorization: Bearer`; no client sends one yet.
- A3. Scheduled jobs only run while the host is up. If the Linux host is a machine that suspends (a laptop), keep it awake on power or schedule wake-ups (`rtcwake`), so jobs run on time.
- A4. Spending limits on the token ledger (`core/usage`): per job run, per job per day, per conversation and overall per day. Checked before every model call; going over ends the run cleanly (a job run is recorded as over budget, a chat gets a clear message), and a warning at a threshold (80%) goes to Telegram or Slack.
- A27. Updating lo9i from the app: the Host card (Settings → System, `/host`) shows the version but can't check for or install a newer one. `scripts/deploy.sh` copies files without `.git` and the version stays 0.1.0, so a host has nothing to compare against. Needs a source of versions (the repository's commits or tags), a check, and an update that pulls, syncs and restarts the daemon (`/system/restart`).
- A30. A web app tab open across a daemon restart keeps running the page it loaded: after an update with a new web build it shows events the old way until reloaded (thinking streamed as one item per piece, before the reload). Give the build an id (in `/health` or the `/events` hello) and have the page offer a reload, or reload itself between runs, when it changes.
- A36. The daemon's output file (`~/.lo9i/logs/output.log`) never rotates: launchd, or the terminal app that started the daemon, opened it for the daemon's stdout and stderr, so it grows for as long as it's used. Rotate it at start (the daemon can point its own stdout and stderr at a new file, as `daemon/launchd.py::move_legacy_output` does) or cap it.
- A37. A LaunchDaemon installed before the logs moved still sends the daemon's output to `~/.lo9i/daemon.log`; the daemon moves it to `output.log` at start (`daemon/launchd.py::move_legacy_output`), but whatever it printed before that (an import error) stays in the old file, which the Logs page doesn't show. The Startup card (both apps) could say the LaunchDaemon is out of date and offer to install it again (one password dialog).
- A38. The journal reader (`core/logs/journal.py`) is tested only against a fake `journalctl`. Check on the Linux host that `journalctl --user-unit lo9i-assistant` run as the daemon's user reads the service's output and systemd's notes about it, whatever the journal's storage there.

## MCP

- A7. Requests from MCP servers: elicitation (a form for the user, through the approval surface on every channel) and sampling (the server asks the model for text; rate-limited, with a token cap). Both are refused today.
- A8. MCP resources and prompts: per-server `list_resources`, `read_resource`, `list_prompts`, `get_prompt` tools, added only when the server supports them and the user turns them on.
- A9. MCP startup: limit how many servers connect at once when the daemon starts. Local servers whose tools are known start on demand (`core/mcp/on_demand.py`); remote servers, and local ones whose tools aren't known yet, all connect at start.
- A12. Signing in to a remote MCP server whose authorization server has no dynamic client registration: today the sign-in fails at registration (`core/mcp/oauth.py`). The Sign in dialog takes a client ID and secret of the user's own OAuth app, saved as the server's registered client so registration is skipped, and shows the redirect URI to register with it, as email does. A client metadata URL (the spec's other option) doesn't fit: the authorization server must fetch it, and the daemon is reachable only on the tailnet.
- A34. Remote MCP servers can't report finished background work: on the 2026-07-28 protocol a streamable HTTP connection has no channel outside a request, so `notifications/lo9i/work_finished` (`core/mcp/background.py`) arrives only from local (stdio) servers. Open a `subscriptions/listen` stream to remote servers that advertise it, if the SDK lets vendor notifications through one.

## Plugins

- A39. The contacts plugin (extras, `communications/contacts/contacts`) reads only the Mac's Contacts, so a Linux host has no contacts. Add a CardDAV source (iCloud, Google Contacts) behind the same `find_contact`, with the account's credentials as the plugin's fields.
- A19. A plugin's token is checked only when it's first used: a wrong Claude key fails the first coding task after about three minutes of Claude Code's retries. Let a plugin declare a check that runs when its fields are saved (a command or a tool), and show its error in the install dialog.
- A28. The private watchlist's downloads (lo9i-assistant-extras-private) record that a magnet was sent to Transmission, not that its files arrived: a torrent that stalls or is removed still shows as downloaded. Read the torrent's state from Transmission (`torrent-get` by info hash, which each download keeps) and show it.
- A25. Kept plugin keys can't be seen or deleted later: the Keep or Delete question after a removal is the only place. A Keys list in Settings (both apps), naming each removed plugin's kept keys and private repository tokens, with Delete.
- A20. Calls (the phone plugin) and anything else that opens an app need lo9i in the user's login session: from boot (`/startup`, a LaunchDaemon) `open` has no screen. Run the daemon as a LaunchAgent in the user's session on macOS, or keep a helper there for what needs the screen.
- A15. Plugins repeat the code their protocol needs: Telegram and Slack each have `daemon.py` and `runner.py`, Claude Code and Copilot each have `task_folder.py`. A change to a protocol means changing every copy. Check them against each other in the extras' tests, or publish one small client per protocol on PyPI.

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
- R2. MCP servers send text the model reads (tool descriptions and results). Hidden Unicode tag characters are stripped and write tools on untrusted servers need approval, but visible injected instructions still reach the model. A server whose tool list keeps changing starts a new epoch at each message (a prompt cache miss each time). A server also names the conversation its finished background work is told to by sending back the call's `_meta["lo9i/origin"]` (`core/mcp/background.py`), which isn't signed: it can put a note in any conversation whose id it learned from a call.
- R3. The private watchlist server (lo9i-assistant-extras-private) is trusted, so its `download` tool starts a torrent without approval. A magnet in text the agent read (a web page, an email) could start a download the user never asked for. Options: mark `download` as needing approval while the rest of the server stays trusted, or only accept magnets the user sent.
- Langfuse: run the self-hosted stack and set keys.
