# Backlog

Open work, tackled one at a time. Finished items are deleted and the remaining codes renumbered.
A = action, G = memory gap, H = context improvement, Q = open question, R = risk.

## Owner's tasks

- A1. Test with a real Anthropic API key (also confirms caching via `cache_read_input_tokens`).

## Next, in order

1. A2. Web UI (SvelteKit) as a daemon client (includes G3 once Q1 is answered).
2. A3. Read email: tools to check, search and read messages over IMAP, using the /email settings.
3. A4. New-mail notifications: an adapter keeps an IMAP IDLE connection open and pushes new mail to Telegram, or starts a job.
4. A5. Approvals for scheduled runs through Telegram instead of automatic denial. Messages the agent sends with `send_message` aren't part of the Telegram conversation yet, so a reply to one arrives without its context; add them to the Telegram thread.
5. G2. Memory search.
6. G4. Prune old checkpoints.

## Email

- A12. OAuth sign-in for email, alongside the password sign-in `/email` has now. Needed for Outlook.com and Microsoft 365 (they only allow OAuth) and for Gmail accounts without app passwords. Same SMTP and IMAP code; only the login changes (XOAUTH2 with a token instead of a password).
  - The saved email settings record the sign-in method: password or OAuth. Presets for Google and Microsoft: servers, ports, sign-in URLs, scopes.
  - The user registers their own OAuth app once (Google Cloud Console "Desktop app", Microsoft Entra app registration) and pastes its client id: a shared app would need Google's paid review for Gmail scopes.
  - Sign-in through the daemon API (so the web UI can offer it too): open the provider's page in the browser, receive the code on localhost, keep tokens in the Store and refresh them. Google tokens expire after 7 days while the consent screen is in "Testing"; set it to "In production".
  - Reference: Hermes Agent's Google Workspace skill (OAuth with PKCE, token file, automatic refresh).

## Daemon

- A6. Restart or stop the daemon from the app.
- A7. Network access, follow-ups. HTTPS and device pairing are done (`daemon/auth.py`, `daemon/https.py`); left:
  - Passkeys as a faster sign-in for paired devices.
  - Bearer tokens for non-browser clients on other hosts (the terminal app over the network). The daemon already accepts `Authorization: Bearer`; no client sends one yet.
- A8. Scheduled jobs only run while the host is up. If the Linux host is a machine that suspends (a laptop), keep it awake on power or schedule wake-ups (`rtcwake`), so jobs run on time.
- A9. Spending limits for scheduled jobs (tokens per run and per day).
- A13. Start at boot on Linux. `/startup` (and Settings → General → Start at boot) installs macOS LaunchDaemons today; on Linux it should install a systemd service for the daemon (and Ollama when `.env` uses it), behind the same daemon API so both clients keep the control. Decide between a system unit running as the owner's user (needs root once, like the macOS administrator prompt) and a user unit with lingering enabled.

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

- A10. Text to speech: optional spoken replies (Telegram voice message, UI playback).
- A11. Real-time voice agent: live spoken conversation from the browser.
  - A speech-to-speech model (OpenAI GPT-Live) listens and speaks. No separate speech-to-text or text-to-speech step; transcripts come from the model's own events.
  - Audio goes directly between the browser and OpenAI over WebRTC. The daemon only exchanges the connection offer and answer, and never handles audio.
  - The daemon keeps a sideband WebSocket to OpenAI for each call. When the voice model needs to act, it calls a tool; the daemon runs it through `AssistantService`, so Claude stays the brain.
  - Tool calls are logged by the model's call id, so a retried call returns the first result.
  - Needs an OpenAI key in addition to the Anthropic key. Not needed for Telegram voice notes.

## Open questions and risks

- Q1. Memory management UI: view, edit, delete.
- R1. Bash runs on the host as the daemon's user. It can read `~/.lo9i` (including the database with the Telegram token and the email password) and that user's other files. Only dangerous-command approvals stand in the way. With remote access (A7), a stolen paired device can reach this too until it's revoked. Options: run the daemon as a dedicated user with little else on the host, and run just the bash tool in a sandbox container.
- Langfuse: run the self-hosted stack and set keys.
