# Backlog

Open work, tackled one at a time. Finished items are deleted and the remaining codes renumbered. Items waiting
for something to happen before they're worth doing are under To revisit, with what brings them back.
A = action, G = memory gap, H = context improvement, Q = open question, R = risk.

## Agent

- A11. Named subagents (a researcher, a coder) as plugins from the extras with an `agent:` section in server.yaml: their own prompt, tools and model.
- A12. Subagents in scheduled jobs. Approvals inside a delegated task follow the job's forwarding rules (`core/approvals.py`).
- A14. A message routed to a conversation with an approval waiting isn't run: the approval is shown again (`core/agent/runs.py::_run_events`; on a channel with its buttons, which answer it), and the message is dropped. An approval waiting in the inbox (a quick question that needed one) holds up every message written outside a conversation, from every client. Let the message through and answer the approval as rejected, or keep the message and run it once the approval is answered.
- A15. Pinning skills from Telegram and Slack. The web and terminal apps pin with `/pin` and `/unpin` (`core/conversation/pinned.py`); channels' commands go to `POST /channels/<name>/commands` (`core/channels/chat/conversations.py`), which needs `pin` and `unpin`, and each plugin has to register them with its service (Telegram's command list, Slack's manifest).
- A19. The plain REPL's /claude (pipes) offers only the workspace and the folders used before, with no browsing, unlike the apps' folder picker (`core/conversation/agent_folders.py`). Add browsing there if it's needed.
- A21. Files sent to a handed-off agent reach it as full paths under `~/.lo9i/uploads`, outside the folder it works in. Claude Code reads them (`bypassPermissions`); the Copilot CLI may refuse paths outside its folder with only `--allow-all-tools`. Check it on a computer with Copilot and pass the uploads folder (`--add-dir`) if needed.
- A18. A channel's turn stops showing in its chat when the channel's stream drops mid-turn (its process restarts after a plugin update): each chat operation fails at once while it's away (`core/channels/hub.py::operate`), and `ChannelChats` gives up on the turn. The run goes on and the apps show it. Wait for the channel to reconnect for a while, or show the rest of the reply once it's back.
- A28. Parallel conversations are only in the web app, on a wide screen: the terminal app holds one conversation (`clients/terminal/.../tui/app.py`), and on a phone the sidebar hides the open list. Give the terminal app a list of open conversations it switches between, and the phone a way to reach the list.
- A29. Routing from the inbox asks the worker model for every message the follow-up rule doesn't settle (`core/conversation/dispatch.py`, among the conversations its words match, those closest in meaning and the most recent). Measure a small classifier like Jev against it on logged picks, and use it where it's as good, so most messages are routed without a model call.
- A30. A channel (Telegram, Slack) can't move a message the inbox sent on to the wrong conversation: `/move` is in the web and terminal apps only, because a channel's command (`POST /channels/<name>/commands`) carries no chat to show the question in. Add the chat to the command in the channel protocol, then `/move` there too.
- A31. On Slack, a reply in a thread goes on in its conversation, but the answer is posted in the DM, not in the thread (the channel plugin's `send` has no thread). Telegram doesn't quote the message either. Send the answer as a reply to the user's message (an optional `reply_to` on the `send` operation) so the chat reads as threads.
- A33. Only the Copilot and OpenAI-compatible models use connections that notice when they died (`core/llm/connections.py`, TCP keepalive): a call to Anthropic or a provider built by `init_chat_model` that's in flight while the computer sleeps waits on its dead connection for its read timeout counted in time awake, hours on a laptop that sleeps (the worker model's titles, digests and routing). `ChatAnthropic` builds its own HTTP client (`_async_client`) with no way to pass one; give it one when langchain-anthropic allows it, or set keepalive on its sockets another way.
- A35. Home (`core/home/`) is only in the web app. Give the terminal app a `/home` screen with the sections, Refresh and editing; the Python `DaemonClient` has `client.home` for it.
- A36. Home's items link only to the section's plugin page, not to the item (the watchlist title, the bill), because the plugins' pages have no addresses for one item. Once a page takes one (`/watchlist/title/<id>`), let the format carry an item's id and link to it.
- A34. A message the assistant starts in the user's own chat on Telegram (`send_message`, the end of background work) goes to every paired account, but lo9i keeps only the last one's message id (the plugin returns one), so replying to it from another paired account goes to the inbox instead of its conversation. Return every copy's id from the plugin's `send` (in the protocol) and keep them all.
- A46. History sends the assistant's own tool calls as a preview that loads in full when opened (`core/conversation/display.py::_preview`, `GET /conversations/<id>/tool-calls/<call id>`), but a delegate or task_status call's answer, its subagent's steps (each output up to 4000 characters, `core/subagent_steps.py`) and a handed-off agent's tool outputs still come whole with every load of the conversation. Preview them the same way, loading a step in full by its call and position.

## Daemon

- A1. Network access, follow-ups. HTTPS and device pairing are done (`daemon/auth.py`, `daemon/https.py`); left:
  - Passkeys as a faster sign-in for paired devices.
  - Bearer tokens for non-browser clients on other hosts (the terminal app over the network). The daemon already accepts `Authorization: Bearer`; no client sends one yet.
- A2. Spending limits on the token ledger (`core/usage`): per job run, per job per day, per conversation and overall per day. Checked before every model call; going over ends the run cleanly (a job run is recorded as over budget, a chat gets a clear message), and a warning at a threshold (80%) goes to Telegram or Slack.
- A24. A LaunchDaemon installed before the logs moved still sends the daemon's output to `~/.lo9i/daemon.log`; the daemon moves it to `output.log` at start (`daemon/launchd.py::move_legacy_output`), but whatever it printed before that (an import error) stays in the old file, which the Logs page doesn't show. The Startup card (both apps) could say the LaunchDaemon is out of date and offer to install it again (one password dialog). The same goes for a LaunchDaemon installed before the daemon could be stopped from the app: its `KeepAlive` restarts it whatever its exit, so Stop is refused until start at boot is turned off and on (`daemon/launchd.py::Service`); the Host card offers Stop and only says so when it's pressed.
- A25. The journal reader (`core/logs/journal.py`) is tested only against a fake `journalctl`. Check on the Linux host that `journalctl --user-unit lo9i-assistant` run as the daemon's user reads the service's output and systemd's notes about it, whatever the journal's storage there.
- A27. Telegram and Slack show only the runs their chat starts: a run the daemon starts in their conversation, like a coding task handed to its agent from a conversation or a follow-up on background work that failed (`daemon/queued.py`), shows in the apps but not in the chat, which hears only the end notice. Show runs started elsewhere in a channel's conversation the way the apps mirror them.
- A32. `tests/core/test_handoffs.py::test_a_restart_waits_until_the_agent_has_replied` fails now and then in the full suite (twice on 2026-10-13, passing alone), as does `tests/core/test_channels.py::test_a_channel_processs_output_is_logged_as_the_channels` (2026-10-17, once in three runs alone), and since the files sent to a working agent (2026-10-24, one in three runs of `test_handoffs.py` alone, on main too) `test_the_agent_gets_the_full_paths_of_the_files_sent_and_the_conversation_keeps_them` and `test_messages_the_agent_ended_without_taking_are_answered_next_in_its_session` (and `test_only_an_agent_at_work_that_takes_messages_gets_them`, once in the full suite on 2026-10-24), whose worker ends without a reply: a timing it waits on without an event. Find what it races with and wait for that instead.
- A42. An update (`daemon/updates.py`) changes lo9i's files while the old daemon still runs: from its `git merge` to the restart, which waits for the runs in progress, modules the daemon imports late and the rebuilt web app served from `daemon/webui` are the new ones, so a tab that reloads then gets the new web app against the old daemon. Build and sync into a staging copy and switch to it at the restart, or restart into the update before anything is served from it.
- A43. An update that fails after its `git merge` (the dependencies or the web build) leaves the new commits checked out with what the old ones needed, and the next restart runs them. Go back to the commit it came from (`ORIG_HEAD`) and what it had installed, or say in the Host card that a restart now would run the half-installed version.
- A44. While a restart or stop is pending (`daemon/shutdown.py`), new runs still start (a scheduled job, a queued follow-up, a message) and it waits for them too, so a busy daemon keeps putting it off; Now cancels only the runs in progress at that moment. Hold new runs while one is pending, and start them after the restart.
- A45. On macOS a daemon started by hand while start at boot is on can't be stopped from the apps (`launchd.Beside` refuses): launchd keeps trying to start the LaunchDaemon, and stopping its tries needs an administrator. Ask for the password, as turning start at boot on does, and stop them.

## MCP

- A5. Requests from MCP servers: elicitation (a form for the user, through the approval surface on every channel) and sampling (the server asks the model for text; rate-limited, with a token cap). Both are refused today.
- A6. MCP resources and prompts: per-server `list_resources`, `read_resource`, `list_prompts`, `get_prompt` tools, added only when the server supports them and the user turns them on.
- A7. MCP startup: limit how many servers connect at once when the daemon starts. Local servers whose tools are known start on demand (`core/mcp/on_demand.py`); remote servers, and local ones whose tools aren't known yet, all connect at start.
- A10. Signing in to a remote MCP server whose authorization server has no dynamic client registration: today the sign-in fails at registration (`core/mcp/oauth.py`). The Sign in dialog takes a client ID and secret of the user's own OAuth app, saved as the server's registered client so registration is skipped, and shows the redirect URI to register with it, as email does. A client metadata URL (the spec's other option) doesn't fit: the authorization server must fetch it, and the daemon is reachable only on the tailnet.
- A23. Remote MCP servers can't report finished background work: on the 2026-07-28 protocol a streamable HTTP connection has no channel outside a request, so `notifications/lo9i/work_finished` (`core/mcp/background.py`) arrives only from local (stdio) servers. Open a `subscriptions/listen` stream to remote servers that advertise it, if the SDK lets vendor notifications through one.

## Plugins

- A26. The contacts plugin (extras, `communications/contacts/contacts`) reads only the Mac's Contacts, so a Linux host has no contacts. Add a CardDAV source (iCloud, Google Contacts) behind the same `find_contact`, with the account's credentials as the plugin's fields.
- A16. A plugin's token is checked only when it's first used: a wrong Claude key fails the first coding task after about three minutes of Claude Code's retries. Let a plugin declare a check that runs when its fields are saved (a command or a tool), and show its error in the install dialog.
- A22. The private watchlist's downloads (lo9i-assistant-extras-private) record that a magnet was sent to Transmission, not that its files arrived: a torrent that stalls or is removed still shows as downloaded. Read the torrent's state from Transmission (`torrent-get` by info hash, which each download keeps) and show it.
- A20. Kept plugin keys can't be seen or deleted later: the Keep or Delete question after a removal is the only place. A Keys list in Settings (both apps), naming each removed plugin's kept keys and private repository tokens, with Delete.
- A17. Calls (the phone plugin) and anything else that opens an app need lo9i in the user's login session: from boot (`/startup`, a LaunchDaemon) `open` has no screen. Run the daemon as a LaunchAgent in the user's session on macOS, or keep a helper there for what needs the screen.
- A37. The hosts plugin (extras, `connectivity/remote/hosts`) hasn't been tried in the web app itself: its page, terminal and reconnects were checked through the pages port and the plugin's page on their own, not in the iframe with a browser's keyboard, sleep and network changes. Try it there, on a phone too.
- A38. The hosts plugin's ssh gets only MCP's default environment (`core/mcp/pages.py`, `get_default_environment`), without `SSH_AUTH_SOCK`: keys held only by an ssh agent (a passphrase key not in the macOS keychain) don't work for its checks and tools, and its terminal asks for the passphrase on every reconnect. Pass the agent's socket to plugins that declare they need it.
- A39. The hosts plugin's `run_command` types into the Herdr session's focused pane and finds the end of a command by an `echo "$?"` marker: it needs a POSIX shell there (not fish), and goes wherever the user moved the focus (another tab or split). Starting a session's headless server waits for its socket to answer (Herdr gives no other sign that it's ready). Give the assistant a pane of its own in the session, named, and wait on Herdr's events when it has one for readiness.
- A40. Requests to a plugin's page are still answered whole within 30 seconds (`daemon/pages.py`): a page that streams a response (Server-Sent Events, a long download) has to use a WebSocket (`daemon/page_sockets.py`) instead. Stream responses through, with the time limit only on the wait for the first byte.
- A41. Plugin pages follow only the dark theme: they're their own origin, so they can't read the web app's theme (`lib/theme.svelte.ts`), and the hosts page copies the app's dark tokens. In the light theme its frame (`routes/pages/[name]/+page.svelte`) shows a dark page. Tell the page the theme (a query parameter on its URL, or a message to the frame) and give the extras' pages both.

## Context

- H1. Better epoch summaries: quote user messages verbatim, keep ids and paths exactly, and let `search_memory` search tool outputs too (it covers only what the user and the assistant wrote).
- H2. The inbox answers quick questions with its whole epoch in context, which holds every message it routed elsewhere and its "→ Continued in …" line (`core/conversation/dispatch_nodes.py`): unrelated topics the model reads past, and tokens spent on each quick answer. Leave routed messages out of the inbox's model calls (`core/conversation/trim.py` stubs them already for tool results), keeping them in its history.
- H3. An edited prompt text (`core/conversation/prompt_edits.py`) hides every later change to its built-in text: an update that adds a rule to `operating.md` never reaches a user who edited it, and nothing says so. Keep the built-in text an edit was made from, and show in Settings → System prompt when the built-in one changed since, with what changed.
- H4. How long a provider's prompt cache lasts is known only for some (`core/llm/providers.py`): Anthropic's 5-minute cache, OpenAI's own API (extended retention, about 30 minutes), DeepSeek (hours). The rest use 5 minutes: Gemini's implicit cache and xAI don't document theirs, Groq caches only its gpt-oss models (2 hours), and a provider with no cache could trim at every user message. Anthropic's 1-hour cache (writes cost 2x the input price instead of 1.25x) isn't offered: a choice in Settings → Model could turn it on, with the lifetime following.

## Voice

- A3. Real-time voice agent: live spoken conversation from the browser.
  - A speech-to-speech model (OpenAI GPT-Live) listens and speaks. No separate speech-to-text or text-to-speech step; transcripts come from the model's own events.
  - Audio goes directly between the browser and OpenAI over WebRTC. The daemon only exchanges the connection offer and answer, and never handles audio.
  - The daemon keeps a sideband WebSocket to OpenAI for each call. When the voice model needs to act, it calls a tool; the daemon runs it through `AssistantService`, so Claude stays the brain.
  - Tool calls are logged by the model's call id, so a retried call returns the first result.
  - Needs an OpenAI key in addition to the Anthropic key. Not needed for Telegram voice notes.
- A4. Spoken replies in Slack. Settings → Audio speaks replies in the web chat and as Telegram voice notes; Slack doesn't get them yet (upload the audio with `files.uploadV2`).


## Platforms

- A8. Windows. Nothing runs there today: the terminal app reaches the daemon only through a Unix socket (`client/connection.py`), and `/startup` knows only launchd and systemd (`daemon/startup.py`).
  - Daemon connection: a named pipe or localhost with a paired device instead of the Unix socket.
  - Startup: a Task Scheduler task or a Windows service as a `daemon/startup.py` backend.
  - Clipboard: `client/clipboard/windows.py`, pasting files, images and text with PowerShell (`Get-Clipboard -Format FileDropList`, `System.Windows.Forms.Clipboard.GetImage`) and copying with `Set-Clipboard`.
  - Bash tool, data paths and `install.sh`: decide between native Windows and running under WSL.

## Languages

- A9. Multi-language support. The app's own text is English only.
  - Interface text: terminal app, web app, and the messages Telegram and Slack adapters send (approval buttons, errors, `/new`). Text kept in per-language files, picked in Settings → General.
  - Prompts in `core/conversation/prompts/` stay in English; the model replies in the user's language.
  - Speech: the speech-to-text language and the Kokoro voice follow the chosen language.
  - Dates and times in the apps use the language's format.

## To revisit

Not worth doing yet; each item says what was done and when to look at it again.

- A13. Plugins repeat the code their protocol needs: Telegram and Slack each have `daemon.py` and `runner.py`, Claude Code and Copilot each have `task_folder.py`, so a protocol change means changing every copy. Done: the extras' `tests/test_shared_code.py` (run by their pre-commit hook) fails when the copies differ, and lists the differences meant to be there. Left: publish one small client per protocol on PyPI, which each plugin's `uv.lock` pins. Revisit when a third channel or agent plugin comes, or a protocol changes again.

## Open questions and risks

- R1. Bash runs on the host as the daemon's user. It can read `~/.lo9i` (including the database with the Telegram token, the email password and MCP servers' keys) and that user's other files. Only dangerous-command approvals stand in the way. With remote access (A1), a stolen paired device can reach this too until it's revoked. A paired device can also add a local MCP server, which runs its command without approval. Options: run the daemon as a dedicated user with little else on the host, and run just the bash tool in a sandbox container.
- R2. MCP servers send text the model reads (tool descriptions and results). Hidden Unicode tag characters are stripped and write tools on untrusted servers need approval, but visible injected instructions still reach the model. A server whose tool list keeps changing starts a new epoch at each message (a prompt cache miss each time). A server also names the conversation its finished background work is told to by sending back the call's `_meta["lo9i/origin"]` (`core/mcp/background.py`), which isn't signed: it can put a note in any conversation whose id it learned from a call.
- R3. The private watchlist server (lo9i-assistant-extras-private) is trusted, so its `download` tool starts a torrent without approval. A magnet in text the agent read (a web page, an email) could start a download the user never asked for. Options: mark `download` as needing approval while the rest of the server stays trusted, or only accept magnets the user sent.
- Langfuse: run the self-hosted stack and set keys.
