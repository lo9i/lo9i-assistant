# AGENTS.md

Personal AI assistant built on LangGraph. A daemon on the Mac owns all state and runs the agent; clients (CLI, web UI) talk to it over HTTP; channel adapters (Telegram) run inside it.

## Layout

```
src/assistant/
  core/          graph, llm, storage (SQLite), observability
    agent/       AssistantService facade + one mixin per concern
    conversation/  system prompt, epochs (compaction), digest, transcript, turn header
      prompts/   prompt texts, one .md file per prompt
    memory/      long-term memory in the Store: profile, facts, episodes
    tools/       self-registering tools
    integrations/  settings for services connected from the app (Telegram, email)
    skills/      reusable instructions as ~/.lo9i/skills/<name>/SKILL.md
    jobs/        scheduled jobs (cron) and their records
    speech/      speech to text (faster-whisper); voice audio saved under uploads/audio
    web/         web search (public engines via ddgs, or the Brave API), page fetching and rendering, URL safety, caching
  daemon/        HTTP API (Unix socket + localhost), run hub (SSE events), adapter supervisor, scheduler, launchd
  client/        connection.py (connect, auto-starts the daemon), sse.py, errors.py (DaemonUnavailableError),
                 live.py (LiveConversation), files.py (attach by path), recorder.py (microphone)
    daemon_client/ DaemonClient: the conversation as mixins; every other area as a group (`client.telegram`, `client.email`, ...);
                 reconnect.py (resumable event streams)
  protocol.py    event JSON shared by daemon and clients
  gateways/      cli/ (a daemon client), telegram/ (an adapter inside the daemon)
```

## Architecture rules

- The daemon is the only process that opens storage or runs the agent. Clients never import `core.agent.AssistantService`; they use `DaemonClient` over HTTP. Conversation calls (`session`, `new_thread`, `send`, `resume`, `events`) sit on the client; every other area is a group named after the part of the daemon it changes (`client.telegram.connect(token)`). New routes go in their area's group, or a new group. Screens receive only the group they use.
- Dependencies point one way: clients -> daemon API -> `core.agent` -> graph -> tools. Core never imports from the daemon, clients or gateways.
- Adapters (Telegram) run inside the daemon as supervised tasks and call `AssistantService` directly. They use only `AssistantService`, `Session`, `MemorySnapshot`, `TelegramStatus`, `InvalidTokenError` (`core/agent`), `Attachment`, `DeliveryError` (`core/outbox.py`) and the event types.
- Messages the agent starts itself (`send_message`) go through `service.outbox`: an adapter registers a sender for its channel while it can deliver and removes it when it stops. The tool calls the sender directly, so it reports real success or failure.
- Every daemon request except `/health` must carry the `X-Lo9i-Client` header (CSRF protection for the localhost port).
- Clients learn about background changes from `GET /events` (the `EventBus` in `core/bus.py`), never by polling. Store writes publish automatically (`NotifyingStore`); other changes (skills, job results, runs, bot state) publish explicitly.
- Clients keep running when the daemon is unreachable (`DaemonUnavailableError`). In the terminal app, every handler that calls the daemon is decorated with `@reports_daemon_unavailable` (`gateways/cli/tui/daemon_errors.py`).
- Runs outlive the request that started them. Commands are HTTP requests; a run's events stream as Server-Sent Events and can be replayed by event id.
- Never edit or delete past messages in a checkpoint. History is append-only.
- Messages use LangChain standard content blocks (`output_version="v1"` in `core/llm.py`). Code that reads messages uses standard block types, never provider-native ones.
- Checkpoints never hold file contents. Attachments are saved under `settings.uploads_dir` and messages keep a `non_standard` upload reference; `core/attachments.py::hydrate` loads them for each model call.
- The system prompt and tool list stay byte-identical within an epoch, so the prompt cache keeps hitting. The system prompt is built when an epoch starts (`core/conversation/epochs.py`) and stored in graph state. Memory changes take effect in the next epoch.
- Prompt texts live in `core/conversation/prompts/`, one `.md` file per prompt, loaded with `prompts.load(name)`. Code doesn't embed prompt text. Tool docstrings and schema field descriptions stay in code.
- Per-turn context (date, time, channel) goes in the turn header at the start of each user message, never in the system prompt.
- A new epoch starts only at a user-message boundary, so tool calls and their results are never split.
- Renaming the assistant (`core/identity.py`, `/name` or the `rename_assistant` tool) starts a new epoch at the next user message: the system prompt is rebuilt with the new name and nothing is summarized. The Telegram bot's display name follows the name.
- Starting a new conversation archives the one being left in the background (`core/agent/archive.py`): an episode plus profile and fact updates, skipped below `EPISODE_MIN_TURNS`.
- Tools register themselves with `@register("<toolset>")` in a module under `core/tools/`. Enabled toolsets come from settings, never per channel, because a conversation spans channels.
- Prefer bash or MCP over a new tool. Every tool definition is sent on every model call.
- Actions that need approval go through `core/tools/approval.py::ask`: bash commands matching `bash_guard.py`, email to recipients outside the allowlist. In unattended runs (channel `worker`, scheduled jobs) they are denied instead, and the job is recorded as needing attention.
- Jobs repeat on a cron `schedule` or run once `at` a local time, then turn themselves off. Scheduled jobs run in their own conversation (`job:<name>:<time>`), are never archived as episodes, and only run while the daemon runs. `/startup` installs LaunchDaemons so the daemon (and Ollama) run from boot.

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

- Python 3.12, managed with `uv`. Add dependencies with `uv add`, never pip.
- Before every commit run `uv run ruff format`, `uv run ruff check` and `uv run pyright`; all must pass. Fix findings instead of disabling rules. A `# pyright: ignore` is only for a verified defect in a library's types, with a comment saying which.
- Tests live in `tests/`, one folder per area (core, web, daemon, telegram, cli). Run `uv run pytest` before every commit; it is offline and uses temporary data paths, never `~/.lo9i`. `uv run pytest -m live` runs the tests that need the network or large downloads (search engines, Telegram, page rendering, the speech model).
- New behavior comes with tests. Use the fixtures in `tests/conftest.py`: `script` (fake model replies), `digests` (fake epoch digests), `service`, and `tests/cli/conftest.py` for the terminal app.
- Run locally: `scripts/run.sh` (starts Ollama when `.env` points at it, then the CLI, which starts the daemon). Nothing runs in Docker. `assistant daemon` runs the daemon in the foreground; its background log is `~/.lo9i/daemon.log`.
- Data lives in `~/.lo9i`: `lo9i.db` (SQLite), `uploads/`, `models/`, `workspace/` (bash), `browsers/` (headless Chromium for page rendering), `SOUL.md`, `daemon.sock`, `daemon.log`, `cli_history` (the terminal app's input history, kept by the client).
- Telegram is connected from the app with `/telegram`; its token and paired accounts live in the Store (`core/integrations/`), not in `.env`.
- Never require the user to run shell commands for app features. Setup flows go through the daemon API so every client, including the web UI, can offer them.

## Backlog

Planned work lives in `BACKLOG.md`. Add new items there. When an item is finished, delete it and renumber the remaining codes in that category, including references to them.
