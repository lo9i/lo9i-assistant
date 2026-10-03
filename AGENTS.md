# AGENTS.md

Personal AI assistant built on LangGraph. A daemon on the Mac owns all state and runs the agent; clients (the terminal app and the web app, in `clients/`) talk to it over HTTP; channel adapters (Telegram, Slack) run inside it.

## Layout

```
src/assistant/
  core/          graph, storage (SQLite), observability
    llm/         chat models per provider (Anthropic, OpenAI, GitHub Copilot)
    agent/       AssistantService facade + one mixin per concern
    conversation/  system prompt, epochs (compaction), digest, transcript, turn header
      prompts/   prompt texts, one .md file per prompt
    memory/      long-term memory in the Store: profile, facts, episodes
    tools/       self-registering tools
    integrations/  services connected from the app, one package each: email/ (accounts, providers, smtp, imap),
                 slack/ (connection, workspace), telegram/ (connection)
    accounts.py  connected accounts per kind (email now), one default per kind; secret_store.py keeps their passwords and tokens encrypted
    skills/      reusable instructions as ~/.lo9i/skills/<name>/SKILL.md, with optional files (scripts, references)
    repositories/  installing skills and MCP servers from git repositories: download, copy, install record
    jobs/        scheduled jobs (cron) and their records
    mcp/         MCP servers: settings (Store), connections (hub), their tools as LangChain tools,
                 installing them from a repository (server.yaml; code under ~/.lo9i/mcp/<name>, data under
                 ~/.lo9i/data/<name>), their web pages (pages.py)
    speech/      speech to text (faster-whisper) and spoken replies (Kokoro), set in Settings → Audio; voice audio saved under uploads/audio
    internet/    the agent's internet access: web search (public engines via ddgs, or the Brave API), page fetching
                 and rendering, URL safety, caching
  daemon/        HTTP API (Unix socket, localhost, HTTPS), device auth, run hub (SSE events), adapter supervisor, scheduler, mail watcher, launchd
  client/        connection.py (connect, auto-starts the daemon), sse.py, errors.py (DaemonUnavailableError),
                 live.py (LiveConversation), files.py (attach by path), recorder.py (microphone)
    daemon_client/ DaemonClient: the conversation as mixins; every other area as a group (`client.telegram`, `client.email`, ...);
                 reconnect.py (resumable event streams)
  protocol.py    event JSON shared by daemon and clients
  gateways/      telegram/ and slack/ (adapters inside the daemon), chat/ (what chat adapters share: turn rendering,
                 approval buttons, splitting)
clients/         the apps, each a daemon client
  terminal/      the terminal app (Textual), its own package `assistant_terminal` in the uv workspace; `assistant` opens it
  web/           the web app (SvelteKit); `npm run build` writes it into src/assistant/daemon/webui, served at /app/
```

## Architecture rules

- The daemon is the only process that opens storage or runs the agent. Clients never import `core.agent.AssistantService`; they use `DaemonClient` over HTTP. Conversation calls (`session`, `new_thread`, `send`, `resume`, `events`) sit on the client; every other area is a group named after the part of the daemon it changes (`client.telegram.connect(token)`). New routes go in their area's group, or a new group. Screens receive only the group they use.
- Dependencies point one way: clients -> daemon API -> `core.agent` -> graph -> tools. Core never imports from the daemon, clients or gateways.
- Adapters (Telegram, Slack) run inside the daemon as supervised tasks and call `AssistantService` directly. They use only `AssistantService`, `Session`, `MemorySnapshot`, `TelegramStatus`, `InvalidTokenError`, `SynthesisError` (`core/agent`), `Attachment`, `DeliveryError` (`core/outbox.py`), `service.approvals` (`core/approvals.py`) and the event types.
- Messages the agent starts itself (`send_message`) go through `service.outbox`: an adapter registers a sender for its channel while it can deliver and removes it when it stops. The tool calls the sender directly, so it reports real success or failure.
- Every daemon request except `/health` must carry the `X-Lo9i-Client` header (CSRF protection for the network ports). The pages port is the exception: browsers load pages there directly, and the `SameSite=Strict` device cookie it requires is what stops other sites.
- Email can sign in with OAuth (Google, Microsoft) through the user's own OAuth app (`core/integrations/email/oauth.py`): the browser comes back to the web app's `/app/oauth` page, which posts the one-time state and the code to `/integrations/email/oauth/finish`. That route is open without a paired device (the state is the proof), so the terminal app's sign-in works from a browser on the host that was never paired. The refresh token is the account's secret; access tokens are refreshed when an account is loaded.
- Only the Unix socket is trusted (`daemon/auth.py::trusted`). Every network request, on localhost or HTTPS, needs a paired device: a one-time code from a trusted client, then a token in an `httpOnly` cookie. Never trust 127.0.0.1: port forwarding and proxies make remote traffic arrive from there. Tokens and codes are stored only as hashes (`core/devices.py`).
- Clients learn about background changes from `GET /events` (the `EventBus` in `core/bus.py`), never by polling. Store writes publish automatically (`NotifyingStore`); other changes (skills, job results, runs, bot state) publish explicitly.
- Clients keep running when the daemon is unreachable (`DaemonUnavailableError`). In the terminal app, every handler that calls the daemon is decorated with `@reports_daemon_unavailable` (`clients/terminal/src/assistant_terminal/tui/daemon_errors.py`).
- Runs outlive the request that started them. Commands are HTTP requests; a run's events stream as Server-Sent Events and can be replayed by event id.
- Never edit or delete past messages in a checkpoint. History is append-only. The one exception is deleting a whole conversation when the user asks (`delete_conversation`): its checkpoints, list entry, search entries and files go, while memory learned from it stays.
- Messages use LangChain standard content blocks (`output_version="v1"` in `core/llm/`). Code that reads messages uses standard block types, never provider-native ones.
- Checkpoints never hold file contents. Attachments are saved under `settings.uploads_dir` and messages keep a `non_standard` upload reference; `core/attachments.py::hydrate` loads them for each model call. Tool results can carry files too (images from MCP tools, an email's attachments): their references go in the ToolMessage's `artifact` (`response_format="content_and_artifact"`), which LangChain never sends; `hydrate` adds them to the result, or to a user message after the results for providers that take images only in user messages.
- The system prompt and tool list stay byte-identical within an epoch, so the prompt cache keeps hitting. The system prompt is built when an epoch starts (`core/conversation/epochs.py`) and stored in graph state. Memory changes take effect in the next epoch.
- Prompt texts live in `core/conversation/prompts/`, one `.md` file per prompt, loaded with `prompts.load(name)`. Code doesn't embed prompt text. Tool docstrings and schema field descriptions stay in code.
- Per-turn context (date, time, channel) goes in the turn header at the start of each user message, never in the system prompt.
- A new epoch starts only at a user-message boundary, so tool calls and their results are never split.
- Renaming the assistant (`core/identity.py`, `/name` or the `rename_assistant` tool) starts a new epoch at the next user message: the system prompt is rebuilt with the new name and nothing is summarized. The Telegram bot's display name follows the name.
- Each client (terminal, browser tab) holds its own conversation: it starts on a new one and resumes an earlier one with `/conversations`. A browser tab keeps its conversation across reloads. A channel without a client (Telegram, Slack) keeps its current conversation in the Store until its `/new`. Runs are announced with the `client_id` that started them, so every other client on that conversation shows them live.
- A conversation no client is on any more is left and archived in the background (`daemon/clients.py`, `core/agent/archive.py`): right away when its client moves to another, after a grace period when its client disconnects. Archiving adds an episode plus profile and fact updates, covers only what's new since the last archive, and is skipped below `EPISODE_MIN_TURNS`.
- Tools register themselves with `@register("<toolset>")` in a module under `core/tools/`. Enabled toolsets come from settings, never per channel, because a conversation spans channels.
- Every model call is recorded in the token ledger (`core/usage/`: `model_calls` and `token_parts` in SQLite) by a `TokenMeter` set on the model with `llm.metered`, never passed in a call's config (that replaces the run's callbacks and stops streaming). A new place that calls a model attaches a meter with its purpose. The ledger keeps tokens only; `core/usage/prices.py` turns them into money when a report is shown.
- Prefer bash or MCP over a new tool. Every tool definition is sent on every model call.
- New features go in a git repository, not in core: a skill (`skills/<name>/SKILL.md`, optional `scripts/`) when it needs only steps or code without secrets, an MCP server (`mcp/<name>/server.yaml`, format in `core/mcp/install.py`) when it needs secrets, an outside service or a connection that stays open. Core changes only for the assistant itself (channels, memory, models, approvals, the apps).
- The user installs plugins in the app (Plugins in the web app, Install in `/skills` and `/mcp`), never the agent, and only from the assistant's extras repository (`core/repositories/known.py`); the apps offer no other source: installed code runs on this computer. When the agent saves or deletes a skill, `approval.ask` asks the user first, so text the agent read can't plant one.
- MCP servers are added from the app (`/mcp`), never by the agent. Their tools are named `mcp__<server>__<tool>`; the user picks which ones the agent gets. Each epoch freezes the MCP tool definitions in graph state (`mcp_tools`); when they change, the next user message starts a new epoch with nothing summarized, as with a rename. Calls look the tool up live in `McpHub`, so a tool turned off stops working at once. On an untrusted server, tools not marked read-only go through `approval.ask`; after a dropped connection only read-only calls are retried.
- Failures of MCP servers and skills are counted in a row per server and per skill (`core/health.py`, in the Store): failed connection attempts and failed or erroring MCP calls (`core/mcp/connection.py`), and skill scripts that exit non-zero or time out, found by their folder in a bash command (`core/skills/tracker.py`, a run callback reading bash's exit-code artifact). Only a working call or script clears the count. At `FAILING_AFTER` in a row a `failing` event alerts every client, and it becomes an alert (`core/agent/alerts.py`, the web app's Alerts page and sidebar bell) that stays until the user dismisses it or it works again; a turned-off server or deleted skill has none. The /mcp and /skills screens show the count and the last failure. A skill whose SKILL.md header is invalid or whose instructions use files it doesn't have lists its `problems`; such a skill isn't installed, updated or saved.
- An MCP server installed from a repository can come with a web page (`page:` in its server.yaml). `core/mcp/pages.py` runs it on a Unix socket in the server's data folder; `daemon/pages.py` serves it to paired devices on the daemon's port plus one, a separate origin so its scripts can't call the API, removing the device cookie and refusing its cookies. The web app shows it in an iframe from the sidebar.
- Actions that need approval go through `core/tools/approval.py::ask`: bash commands matching `bash_guard.py`, email to recipients outside the allowlist. In unattended runs (channel `worker`, scheduled jobs) the scheduler forwards them to the adapters registered in `service.approvals` (`core/approvals.py`; Telegram, with `ja:`/`jr:` buttons) and waits up to `JOB_APPROVAL_MINUTES`, which doesn't count toward the run's time limit. With no adapter registered, or no answer in time, they are denied and the job is recorded as needing attention.
- Messages the assistant sends on a channel from outside that channel's conversation (`send_message` from a job or another chat, new-mail alerts) are recorded with `core/conversation/sent.py` and go into the turn header of the user's next message on that channel, once.
- The mail watcher (`daemon/mail_watcher.py`) keeps one IMAP IDLE connection open while new-mail alerts or a mail job want it, and hands new messages to `Scheduler.run_for_mail`. The last UID seen is saved before delivery, so restarts never repeat or flood.
- Jobs repeat on a cron `schedule`, run once `at` a local time (then turn themselves off), or run `on_new_mail`. Scheduled jobs run in their own conversation (`job:<name>:<time>`), are never archived as episodes, and only run while the daemon runs. `/startup` makes the daemon run from boot: LaunchDaemons on macOS (with Ollama), a systemd user service on Linux (`daemon/startup.py` picks the backend).

## Code rules

- No quick workarounds or shortcuts. Fix the cause with the right design, even when a stopgap (polling, sleeps, retries, special cases, silenced errors) would be faster. If a proper fix isn't possible yet, say so and add it to `BACKLOG.md` instead of shipping the stopgap.
- Private functions, methods and attributes start with `_`. Anything without `_` is public API of its module.
- Keep functions small and single-purpose. If a function needs a comment to separate its steps, split it into functions. Aim for under ~20 lines.
- Apply SOLID:
  - Single responsibility: one reason to change per class and module.
  - Open/closed: add behavior with new classes or functions (new tool, new gateway) instead of editing unrelated code.
  - Liskov: subclasses and protocol implementations must be usable wherever the base is expected.
  - Interface segregation: small protocols with only the methods callers need.
  - Dependency inversion: depend on abstractions and pass dependencies in (constructor or arguments). No hidden globals beyond `settings`.
- Large classes are a facade composing mixins, one file per concern (see `core/agent/`). Shared attributes are declared on a base class. New behavior goes in a new or matching mixin, never in the facade.
- Type hints on all public signatures.
- Async all the way in core. No blocking I/O in async code.
- Match the style of surrounding code. Comments explain why, not what.

## Tooling

- Python 3.12, managed with `uv` as a workspace: the root package and `clients/terminal`. Add dependencies with `uv add` (`uv add --package assistant-terminal` for the terminal app), never pip.
- Before every commit run `uv run ruff format`, `uv run ruff check` and `uv run pyright`; all must pass. Fix findings instead of disabling rules. A `# pyright: ignore` is only for a verified defect in a library's types, with a comment saying which.
- Tests live in `tests/`, one folder per area (core, internet, daemon, chat, telegram, slack, terminal). Run `uv run pytest` before every commit; it is offline and uses temporary data paths, never `~/.lo9i`. `uv run pytest -m live` runs the tests that need the network or large downloads (search engines, Telegram, Slack, page rendering, the speech model).
- New behavior comes with tests. Use the fixtures in `tests/conftest.py`: `script` (fake model replies), `digests` (fake epoch digests), `service`, and `tests/terminal/conftest.py` for the terminal app.
- Run locally: `scripts/run.sh` (starts Ollama when `.env` points at it, then the terminal app, which starts the daemon). Nothing runs in Docker. `assistant daemon` runs the daemon in the foreground; its background log is `~/.lo9i/daemon.log`.
- Install: `install.sh` at the repo root, piped from curl (clones into `~/lo9i-assistant`) or run in a checkout. It installs uv and the dependencies, asks for the provider and key the first time and writes `.env` on that computer, and on Linux runs the daemon as the same systemd user service `/startup` installs. `scripts/deploy.sh user@host` copies this working tree to a host and runs install.sh there; it never copies `.env`.
- Data lives in `~/.lo9i`: `lo9i.db` (SQLite), `uploads/`, `models/`, `workspace/` (bash), `browsers/` (headless Chromium for page rendering), `SOUL.md`, `daemon.sock`, `daemon.log`, `cli_history` (the terminal app's input history, kept by the client).
- The model (provider, its fields, main and worker model) is set from the app with `/model` or Settings → General → Model, saved in the Store and overriding `.env` (`core/llm/choice.py`). Providers are listed in `core/llm/providers.py`: Anthropic, Copilot and OpenAI-compatible have their own builders, every other one goes through LangChain's `init_chat_model` with the field values as keyword arguments. A provider's package is installed with uv when it's first chosen, or at start if it went missing (`core/llm/packages.py`); `install.sh` syncs with `--inexact` so deploys keep them. Saving asks each model to answer once; the service then rebuilds its graph, digester and titler (`core/agent/model.py`), so the change applies without a restart. Model builders take a `ModelChoice`, never read the provider from `settings`.
- Telegram is connected from the app with `/telegram`, Slack with `/slack`; their tokens and paired accounts live in the Store (`core/integrations/`), not in `.env`. Slack uses Socket Mode, so it needs no public URL.
- Services the user can connect more than once (email now) are accounts (`core/accounts.py`): a Store record per account with its settings, one default per kind. Their passwords and tokens, and the model's API key set in the app (`core/llm/choice.py`), go only through `core/secret_store.py`, encrypted with the key file at `SECRETS_KEY_PATH` (`~/.lo9i/keys/secrets.key`, outside the database), never in a plain Store record. Tools that act on an account take an `account` argument (label, address or id; empty for the default), and the system prompt lists the accounts at the start of each epoch, so the tool list never changes.
- Web UI conventions, including the default page layout, are in `clients/web/WEB.md`. Follow them for new pages.
- Never require the user to run shell commands for app features. Setup flows go through the daemon API so every client, including the web UI, can offer them.

## Backlog

Planned work lives in `BACKLOG.md`. Add new items there. When an item is finished, delete it and renumber the remaining codes in that category, including references to them.
