# Backlog

Open work, tackled one at a time. Finished items are deleted and the remaining codes renumbered. Items waiting
for something to happen before they're worth doing are under To revisit, with what brings them back.
A = action, G = memory gap, H = context improvement, Q = open question, R = risk.

## Agent

- A1. Named subagents (a researcher, a coder) as plugins from the extras with an `agent:` section in server.yaml: their own prompt, tools and model.
- A2. Subagents in scheduled jobs. Approvals inside a delegated task follow the job's forwarding rules (`core/approvals.py`).
- A3. Pinning skills from Telegram and Slack. The web and terminal apps pin with `/pin` and `/unpin` (`core/conversation/pinned.py`); channels' commands go to `POST /channels/<name>/commands` (`core/channels/chat/conversations.py`), which needs `pin` and `unpin`, and each plugin has to register them with its service (Telegram's command list, Slack's manifest).
- A4. The plain REPL's /claude (pipes) offers only the workspace and the folders used before, with no browsing, unlike the apps' folder picker (`core/conversation/agent_folders.py`). Add browsing there if it's needed.
- A5. Routing from the inbox asks the worker model for every message the follow-up rule doesn't settle (`core/conversation/dispatch.py`, among the conversations its words match, those closest in meaning and the most recent). Measure a small classifier like Jev against it on logged picks, and use it where it's as good, so most messages are routed without a model call.
- A6. On Slack, a reply in a thread goes on in its conversation, but the answer is posted in the DM, not in the thread (the channel plugin's `send` has no thread). Telegram doesn't quote the message either. Send the answer as a reply to the user's message (an optional `reply_to` on the `send` operation) so the chat reads as threads.
- A7. Only the Copilot and OpenAI-compatible models use connections that notice when they died (`core/llm/connections.py`, TCP keepalive): a call to Anthropic or a provider built by `init_chat_model` that's in flight while the computer sleeps waits on its dead connection for its read timeout counted in time awake, hours on a laptop that sleeps (the worker model's titles, digests and routing). `ChatAnthropic` builds its own HTTP client (`_async_client`) with no way to pass one; give it one when langchain-anthropic allows it, or set keepalive on its sockets another way.
- A8. Only Claude Code's worker writes `context.json` (`docs/agent-plugins.md`), so conversations handed to the Copilot agent show no context bar (web status bar, the terminal app's footer). The Copilot CLI (1.0.95) writes `--usage-output-file` with `lastCallInputTokens` but no context window; try it on an account with Copilot access (this computer's is restricted) and take the window from the model, as the Claude Code worker does. The agent's context is also as of its last answer, not live while it works (`claude_code_tasks/runner.py::_context`).
- A9. A message the assistant starts in the user's own chat on Telegram (`send_message`, the end of background work) goes to every paired account, but lo9i keeps only the last one's message id (the plugin returns one), so replying to it from another paired account goes to the inbox instead of its conversation. Return every copy's id from the plugin's `send` (in the protocol) and keep them all.
- A10. Only a coding task the assistant wrote for its agent is told apart from the user's messages (`core/conversation/briefs.py`: shown as "Task for <agent>", never pinned). The brief `move_to_conversation` writes when it moves work out of the inbox (`core/tools/side.py::_moved` with no handoff) is the assistant's words too, yet a new conversation shows it as the user's message and pins it over the thread. Mark it the same way, with a label of its own ("From the inbox").
- A11. Answer buttons show only in the web app (`clients/web/src/lib/chat/choices.ts`); Telegram and Slack take the marker out (`core/conversation/choices.py`) and the terminal app too. Give the chat channels tap buttons for a reply's choices (a button operation that sends its text as the user's message, which the channel protocol has for questions' buttons, `core/channels/chat/questions.py`), and the terminal app a way to pick one.
- A12. Home places its cards with `grid-auto-flow: dense` (`clients/web/src/routes/home/+page.svelte`), so a narrow card after a wide one moves up into the hole the wide one left at the end of a row: the page can show the cards in another order than the saved one, and Move up and Move down then seem to move a card past one it isn't next to on screen. Place wide cards where they fit without reordering (pack the order into rows, widening the last card of a row to fill it), or say on the card where it goes.
- A13. Home's sections built by code (`core/home/coded.py`, the Copilot card) open in the same editor as the others, whose What to show and Plugins do nothing for them (the text says so). Say on the section that it's built by code and let the editor change only its title and width.
- A14. The Copilot allowance alerts go only to WhatsApp (`core/copilot_quota/watch.py::CHANNEL`); while it isn't connected an alert waits, and without the plugin it's never sent. Send it on the channels the user picks, or every connected one, and add it to the notifications feed.
- A40. Importing skills from other agents (`core/skills/imports/`) leaves out: Claude Code's commands (`~/.claude/commands/`, a project's `.claude/commands/`) and its plugins' skills, and Codex's admin skills (`/etc/codex/skills`); the question at install is asked only when install.sh runs in a terminal, so a host installed over ssh without one never hears it (the apps' `/import-skills` still lists them), and the plain REPL has no `/import-skills`; and a project skill whose text names the project's own `scripts/` files is refused as using files it doesn't have. Add what's worth it.
- A41. The side panel with the folder a conversation is handed to (`clients/web/src/lib/ui/chat/folder/`, `core/handed_folder/`) is only in the web app: the terminal app can't browse that folder or see what changed there, and the Python `DaemonClient` has no methods for `GET /conversations/<id>/agent/folder`, `.../folder/file` and `.../folder/changes`. The panel also shows a changed file's text, not its diff (`git diff` for it), and lists a folder's files only as they are on disk, so a deleted file shows only in the Changed list.

## Daemon

- A15. Network access, follow-ups. HTTPS and device pairing are done (`daemon/auth.py`, `daemon/https.py`); left:
  - Passkeys as a faster sign-in for paired devices.
  - Bearer tokens for non-browser clients on other hosts (the terminal app over the network). The daemon already accepts `Authorization: Bearer`; no client sends one yet.
- A16. Spending limits on the token ledger (`core/usage`): per job run, per job per day, per conversation and overall per day. Checked before every model call; going over ends the run cleanly (a job run is recorded as over budget, a chat gets a clear message), and a warning at a threshold (80%) goes to Telegram or Slack.
- A17. The journal reader (`core/logs/journal.py`) is tested only against a fake `journalctl`. Check on the Linux host that `journalctl --user-unit lo9i-assistant` run as the daemon's user reads the service's output and systemd's notes about it, whatever the journal's storage there.
- A18. Telegram and Slack show only the runs their chat starts: a run the daemon starts in their conversation, like a coding task handed to its agent from a conversation or a follow-up on background work that failed (`daemon/queued.py`), shows in the apps but not in the chat, which hears only the end notice. Show runs started elsewhere in a channel's conversation the way the apps mirror them.
- A19. On macOS a daemon started by hand while start at boot is on can't be stopped from the apps (`launchd.Beside` refuses): launchd keeps trying to start the LaunchDaemon, and stopping its tries needs an administrator. Ask for the password, as turning start at boot on does, and stop them.
- A20. While an update installs, new runs are refused with a message to send them again once lo9i is back (`hold_runs`, `daemon/updates.py`): the user retypes it, and a scheduled job due then fails with that message. Keep them instead (with their files and the channel they came from) and run them once the daemon has restarted on the update.

## MCP

- A21. Requests from MCP servers: elicitation (a form for the user, through the approval surface on every channel) and sampling (the server asks the model for text; rate-limited, with a token cap). Both are refused today.
- A22. MCP resources and prompts: per-server `list_resources`, `read_resource`, `list_prompts`, `get_prompt` tools, added only when the server supports them and the user turns them on.
- A23. Signing in to a remote MCP server whose authorization server has no dynamic client registration: today the sign-in fails at registration (`core/mcp/oauth.py`). The Sign in dialog takes a client ID and secret of the user's own OAuth app, saved as the server's registered client so registration is skipped, and shows the redirect URI to register with it, as email does. A client metadata URL (the spec's other option) doesn't fit: the authorization server must fetch it, and the daemon is reachable only on the tailnet.
- A24. Remote MCP servers can't report finished background work: on the 2026-07-28 protocol a streamable HTTP connection has no channel outside a request, so `notifications/lo9i/work_finished` (`core/mcp/background.py`) arrives only from local (stdio) servers. Open a `subscriptions/listen` stream to remote servers that advertise it, if the SDK lets vendor notifications through one.
- A25. Subagents (`delegate`) get only the read-only tools of the plugins their conversation loaded (`core/subagent.py`), with no `load_tools` of their own, so a delegated task that needs a plugin the conversation didn't load can't use it. Give subagents `load_tools` if delegated tasks show they need it.

## Plugins

- A26. The contacts plugin (extras, `communications/contacts/contacts`) reads a CardDAV account with a user name and password (iCloud, Fastmail, Nextcloud), but Google Contacts' CardDAV takes only OAuth. Plugins can sign in with the user's own OAuth app now (`oauth:` in server.yaml, `core/mcp/plugin_oauth.py`, as the google-drive plugin does): declare it with Google's contacts scope and use the login in `LO9I_OAUTH` for CardDAV.
- A27. A plugin's token is checked only when it's first used: a wrong Claude key fails the first coding task after about three minutes of Claude Code's retries. Let a plugin declare a check that runs when its fields are saved (a command or a tool), and show its error in the install dialog.
- A28. Calls (the phone plugin) and anything else that opens an app need lo9i in the user's login session: from boot (`/startup`, a LaunchDaemon) `open` has no screen. Run the daemon as a LaunchAgent in the user's session on macOS, or keep a helper there for what needs the screen. It would also give plugins that ask for the ssh agent (`ssh_agent: true`, `core/mcp/ssh_agent.py`) the user's agent, which a LaunchDaemon has none of.
- A29. The hosts plugin (extras, `connectivity/remote/hosts`) hasn't been tried in the web app itself: its page, terminal and reconnects were checked through the pages port and the plugin's page on their own, not in the iframe with a browser's keyboard, sleep and network changes. Try it there, on a phone too.
- A30. YouTube summaries: summarize a video from its transcript (the youtube plugin, `media/video/youtube`, already downloads transcripts), and optionally the new uploads of followed channels in the watchlist.

## Context

- H1. Better epoch summaries: quote user messages verbatim, keep ids and paths exactly, and let `search_memory` search tool outputs too (it covers only what the user and the assistant wrote).
- H2. The groups of core tools load on demand now (email, jobs, skill writing; `core/tools/registry.py::tool_groups`); the longest descriptions are still long (`update_profile`, `move_to_conversation`, `delegate`, `remember`, and in their groups `schedule_job`, `save_skill`, `search_email`). Shorten them, moving their guidance into skills the model reads only when needed (about 0.5–1k tokens).

## Voice

- A31. Real-time voice agent: live spoken conversation from the browser.
  - A speech-to-speech model (OpenAI GPT-Live) listens and speaks. No separate speech-to-text or text-to-speech step; transcripts come from the model's own events.
  - Audio goes directly between the browser and OpenAI over WebRTC. The daemon only exchanges the connection offer and answer, and never handles audio.
  - The daemon keeps a sideband WebSocket to OpenAI for each call. When the voice model needs to act, it calls a tool; the daemon runs it through `AssistantService`, so Claude stays the brain.
  - Tool calls are logged by the model's call id, so a retried call returns the first result.
  - Needs an OpenAI key in addition to the Anthropic key. Not needed for Telegram voice notes.
- A32. Spoken replies in Slack. Settings → Audio speaks replies in the web chat and as Telegram voice notes; Slack doesn't get them yet (upload the audio with `files.uploadV2`).
- A33. A voice message that is the first message of a conversation the web app's Chat opened for no topic (a new tab) stays in that conversation: routing reads only typed text (`POST /routes`, `ChatController.routed`), while the inbox routes a voice note by what it said. Transcribe it first, or let `/routes` take the recording, so it goes on in the conversation it's about too.

## Platforms

- A34. Windows. Nothing runs there today: the terminal app reaches the daemon only through a Unix socket (`client/connection.py`), and `/startup` knows only launchd and systemd (`daemon/startup.py`).
  - Daemon connection: a named pipe or localhost with a paired device instead of the Unix socket.
  - Startup: a Task Scheduler task or a Windows service as a `daemon/startup.py` backend.
  - Clipboard: `client/clipboard/windows.py`, pasting files, images and text with PowerShell (`Get-Clipboard -Format FileDropList`, `System.Windows.Forms.Clipboard.GetImage`) and copying with `Set-Clipboard`.
  - Bash tool, data paths and `install.sh`: decide between native Windows and running under WSL.
- A35. The agent-finished pop-up on Android. Chrome there grants the notification permission but shows notifications only from a service worker (`ServiceWorkerRegistration.showNotification`); `new Notification` throws, so the web app shows its own notice instead (`lib/agentDone.svelte.ts::systemNotice`). Needs a service worker (`src/service-worker.ts`, registered by SvelteKit) whose `notificationclick` opens the conversation.

## Languages

- A36. Languages, follow-ups. The apps' own text is in English and Spanish (`core/language.py`, Settings → General, `/language`; `core/i18n/`, `clients/web/src/lib/locales/`, `assistant_terminal/locales/`); left:
  - Text the daemon writes for people is English whatever the language: errors raised in core and shown as they come (HTTP error details, tool and plugin errors), notifications' and alerts' titles and texts, the health check's causes and context parts, background work's end notices, plugin fields' and model providers' labels and help, and built-in Home sections' titles. Give the code that writes them the chosen texts (`i18n.chosen`), as the chat channels' (`core/channels/chat/`), the new-mail alerts and the Copilot card do. The web app's "auto" follows the browser, which the daemon doesn't know, so text it writes for the apps would follow the saved choice only.
  - The chat channel plugins' own text (their setup items, pairing replies; in the extras) is English.
  - The terminal app makes its key bindings and some labels when its modules are imported (`assistant_terminal/i18n.py`), so `/language` changes them from the next start; the plain REPL (pipes) has no `/language`.
  - A third language means a table per place (`core/i18n/<code>.json`, the terminal's `locales/<code>.json`, the web app's `locales/<code>.json`), the code in `core/language.py`, and the cron library's locale for the terminal app (`jobs_text.py::_CRON_LOCALES`).

## To revisit

Not worth doing yet; each item says what was done and when to look at it again.

- A37. Starting the hosts plugin's Herdr session on a host (extras, `connectivity/remote/hosts`, `herdr.py::_READY`) waits for its socket to answer, up to 5 seconds: Herdr 0.9 has no event or command that says a headless server is ready. Done: the assistant's commands run in a tab of their own, labeled `assistant`, with a POSIX sh (hosts 0.4.0). Revisit when Herdr adds a readiness signal (its CLI reference, `herdr status server`, events).
- A38. Plugins repeat the code their protocol needs: Telegram and Slack each have `daemon.py` and `runner.py`, Claude Code and Copilot each have `task_folder.py`, so a protocol change means changing every copy. Done: the extras' `tests/test_shared_code.py` (run by their pre-commit hook) fails when the copies differ, and lists the differences meant to be there. Left: publish one small client per protocol on PyPI, which each plugin's `uv.lock` pins. Revisit when a third channel or agent plugin comes, or a protocol changes again.

- A39. Try NVIDIA Nemotron 3.5 Transcribe (open, 40 languages incl. Spanish, speaker labels, translation, questions about a recording, term hints in the prompt, up to 1 h of audio) in place of faster-whisper, or as a plugin for long recordings such as meetings or YouTube videos without captions. Today it's 30B (4B active) and only runs on a large NVIDIA GPU via vLLM; hosted APIs (DeepInfra, Baseten) send audio to a third party. Revisit when its quantized versions and NeMo-Speech.cpp ship and it runs on a Mac. https://huggingface.co/blog/nvidia/nemotron-transcribe-granary

## Open questions and risks

- R1. Bash runs on the host as the daemon's user. It can read `~/.lo9i` (including the database with the Telegram token, the email password and MCP servers' keys) and that user's other files. Only dangerous-command approvals stand in the way. With remote access (A15), a stolen paired device can reach this too until it's revoked. A paired device can also add a local MCP server, which runs its command without approval. Options: run the daemon as a dedicated user with little else on the host, and run just the bash tool in a sandbox container.
- R2. MCP servers send text the model reads (tool descriptions and results). Hidden Unicode tag characters are stripped and write tools on untrusted servers need approval, but visible injected instructions still reach the model. A server whose tool list keeps changing starts a new epoch at each message (a prompt cache miss each time). A server also names the conversation its finished background work is told to by sending back the call's `_meta["lo9i/origin"]` (`core/mcp/background.py`), which isn't signed: it can put a note in any conversation whose id it learned from a call.
- R3. The private watchlist server (lo9i-assistant-extras-private) is trusted, so its `download` tool starts a torrent without approval. A magnet in text the agent read (a web page, an email) could start a download the user never asked for. Options: mark `download` as needing approval while the rest of the server stays trusted, or only accept magnets the user sent.
- Langfuse: run the self-hosted stack and set keys.
