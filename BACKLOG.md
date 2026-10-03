# Backlog

Open work, tackled one at a time. Finished items are deleted and the remaining codes renumbered.
A = action, G = memory gap, H = context improvement, Q = open question, R = risk.

## Next, in order

1. G2. Memory search.
2. G4. Prune old checkpoints.

## Email

- A6. OAuth sign-in for email, alongside the password sign-in `/email` has now. Needed for Outlook.com and Microsoft 365 (they only allow OAuth) and for Gmail accounts without app passwords. Same SMTP and IMAP code; only the login changes (XOAUTH2 with a token instead of a password).
  - The saved email settings record the sign-in method: password or OAuth. Presets for Google and Microsoft: servers, ports, sign-in URLs, scopes.
  - The user registers their own OAuth app once (Google Cloud Console "Desktop app", Microsoft Entra app registration) and pastes its client id: a shared app would need Google's paid review for Gmail scopes.
  - Sign-in through the daemon API (so the web UI can offer it too): open the provider's page in the browser, receive the code on localhost, keep tokens in the Store and refresh them. Google tokens expire after 7 days while the consent screen is in "Testing"; set it to "In production".
  - Reference: Hermes Agent's Google Workspace skill (OAuth with PKCE, token file, automatic refresh).
- A13. Email attachments: `read_email` lists them by name only. Save them as uploads so the agent can open them, like attachments in chat.

## Daemon

- A1. Restart or stop the daemon from the app.
- A2. Network access, follow-ups. HTTPS and device pairing are done (`daemon/auth.py`, `daemon/https.py`); left:
  - Passkeys as a faster sign-in for paired devices.
  - Bearer tokens for non-browser clients on other hosts (the terminal app over the network). The daemon already accepts `Authorization: Bearer`; no client sends one yet.
- A3. Scheduled jobs only run while the host is up. If the Linux host is a machine that suspends (a laptop), keep it awake on power or schedule wake-ups (`rtcwake`), so jobs run on time.
- A4. Spending limits for scheduled jobs (tokens per run and per day).
- A15. Token usage. Record input, output and cache read/write tokens for every model call (from `usage_metadata`), with the model, conversation, channel and job. Show totals per day, model and conversation in the web Usage page and the terminal's `/usage`, next to tool usage. A4 builds on it.
- A14. A job run waiting for approval on Telegram doesn't survive a daemon restart: its conversation stays paused and the run is never recorded. On start, resume such runs (the answer can still arrive) or record them as needing attention.

## MCP

- A8. OAuth for remote MCP servers (authorization code with PKCE, and device code for a headless host), through the daemon API so both clients can offer it. Tokens in the Store, refreshed automatically; a server whose refresh fails waits for the user to sign in again.
- A9. Requests from MCP servers: elicitation (a form for the user, through the approval surface on every channel) and sampling (the server asks the model for text; rate-limited, with a token cap). Both are refused today.
- A10. MCP resources and prompts: per-server `list_resources`, `read_resource`, `list_prompts`, `get_prompt` tools, added only when the server supports them and the user turns them on.
- A11. Images and audio in MCP tool results. They show as a placeholder today; save them as uploads and let `hydrate` load them in tool messages too.
- A12. MCP startup: start a server on its first call from a cached tool list (for servers that use a lot of memory), and limit how many connect at once when the daemon starts.

## Memory

- G1. Memory extraction runs in the same call as the epoch summary, which delays the reply that starts a new epoch. Move it to a background task after the reply.
- G2. Facts and episodes are loaded up to the configured limits, with no search beyond them.
- G3. No way to view or edit memories (Q1).
- G4. Checkpoints are never pruned.

## Context

- H1. Better epoch summaries: quote user messages verbatim, keep ids and paths exactly, and add a `search_history` tool over the full checkpoint.
- H2. Replace old tool outputs within an epoch with short stubs.
- H3. Tell the digest to ignore instructions found in tool output, so injected text can't reach facts or the profile.

## Voice

- A5. Real-time voice agent: live spoken conversation from the browser.
  - A speech-to-speech model (OpenAI GPT-Live) listens and speaks. No separate speech-to-text or text-to-speech step; transcripts come from the model's own events.
  - Audio goes directly between the browser and OpenAI over WebRTC. The daemon only exchanges the connection offer and answer, and never handles audio.
  - The daemon keeps a sideband WebSocket to OpenAI for each call. When the voice model needs to act, it calls a tool; the daemon runs it through `AssistantService`, so Claude stays the brain.
  - Tool calls are logged by the model's call id, so a retried call returns the first result.
  - Needs an OpenAI key in addition to the Anthropic key. Not needed for Telegram voice notes.
- A7. Spoken replies in Slack. Settings → Audio speaks replies in the web chat and as Telegram voice notes; Slack doesn't get them yet (upload the audio with `files.uploadV2`).

## Chat channels

- A16. Approval requests longer than Telegram's 4096-character limit fail to send (`TelegramChat.send` doesn't split; the request text is a whole bash command or a whole skill with its files). Split the text and put the buttons on the last part.

## Platforms

- A17. Windows. Nothing runs there today: the terminal app reaches the daemon only through a Unix socket (`client/connection.py`), and `/startup` knows only launchd and systemd (`daemon/startup.py`).
  - Daemon connection: a named pipe or localhost with a paired device instead of the Unix socket.
  - Startup: a Task Scheduler task or a Windows service as a `daemon/startup.py` backend.
  - Clipboard: `client/clipboard/windows.py`, pasting files, images and text with PowerShell (`Get-Clipboard -Format FileDropList`, `System.Windows.Forms.Clipboard.GetImage`) and copying with `Set-Clipboard`.
  - Bash tool, data paths and `install.sh`: decide between native Windows and running under WSL.

## Open questions and risks

- Q1. Memory management UI: view, edit, delete.
- R1. Bash runs on the host as the daemon's user. It can read `~/.lo9i` (including the database with the Telegram token, the email password and MCP servers' keys) and that user's other files. Only dangerous-command approvals stand in the way. With remote access (A2), a stolen paired device can reach this too until it's revoked. A paired device can also add a local MCP server, which runs its command without approval. Options: run the daemon as a dedicated user with little else on the host, and run just the bash tool in a sandbox container.
- R2. MCP servers send text the model reads (tool descriptions and results). Hidden Unicode tag characters are stripped and write tools on untrusted servers need approval, but visible injected instructions still reach the model. A server whose tool list keeps changing starts a new epoch at each message (a prompt cache miss each time).
- Langfuse: run the self-hosted stack and set keys.
