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
    integrations/  settings for services connected from the app (Telegram)
    speech/      speech to text (faster-whisper); voice audio saved under uploads/audio
    web/         web search (public engines via ddgs, or the Brave API), page fetching and rendering, URL safety, caching
  daemon/        HTTP API (Unix socket + localhost), run hub (SSE events), adapter supervisor
  client/        DaemonClient: the service's methods over HTTP, auto-starts the daemon
  protocol.py    event JSON shared by daemon and clients
  gateways/      cli/ (a daemon client), telegram/ (an adapter inside the daemon)
```

## Architecture rules

- The daemon is the only process that opens storage or runs the agent. Clients never import `core.agent.AssistantService`; they use `DaemonClient`, which offers the same methods over HTTP.
- Dependencies point one way: clients -> daemon API -> `core.agent` -> graph -> tools. Core never imports from the daemon, clients or gateways.
- Adapters (Telegram) run inside the daemon as supervised tasks and call `AssistantService` directly. They use only `AssistantService`, `Session`, `MemorySnapshot`, `TelegramStatus`, `InvalidToken` (`core/agent`), `Attachment` and the event types.
- Every daemon request except `/health` must carry the `X-Lo9i-Client` header (CSRF protection for the localhost port).
- Runs outlive the request that started them. Commands are HTTP requests; a run's events stream as Server-Sent Events and can be replayed by event id.
- Never edit or delete past messages in a checkpoint. History is append-only.
- Messages use LangChain standard content blocks (`output_version="v1"` in `core/llm.py`). Code that reads messages uses standard block types, never provider-native ones.
- Checkpoints never hold file contents. Attachments are saved under `settings.uploads_dir` and messages keep a `non_standard` upload reference; `core/attachments.py::hydrate` loads them for each model call.
- The system prompt and tool list stay byte-identical within an epoch, so the prompt cache keeps hitting. The system prompt is built when an epoch starts (`core/conversation/epochs.py`) and stored in graph state. Memory changes take effect in the next epoch.
- Prompt texts live in `core/conversation/prompts/`, one `.md` file per prompt, loaded with `prompts.load(name)`. Code doesn't embed prompt text. Tool docstrings and schema field descriptions stay in code.
- Per-turn context (date, time, channel) goes in the turn header at the start of each user message, never in the system prompt.
- A new epoch starts only at a user-message boundary, so tool calls and their results are never split.
- Tools register themselves with `@register("<toolset>")` in a module under `core/tools/`. Enabled toolsets come from settings, never per channel, because a conversation spans channels.
- Prefer bash or MCP over a new tool. Every tool definition is sent on every model call.
- Bash commands matching `core/tools/bash_guard.py` require approval via `interrupt()`.

## Code rules

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
- Run locally: `scripts/run.sh` (starts Ollama when `.env` points at it, then the CLI, which starts the daemon). Nothing runs in Docker. `assistant daemon` runs the daemon in the foreground; its background log is `~/.lo9i/daemon.log`.
- Data lives in `~/.lo9i`: `lo9i.db` (SQLite), `uploads/`, `models/`, `workspace/` (bash), `browsers/` (headless Chromium for page rendering), `SOUL.md`, `daemon.sock`, `daemon.log`.
- Telegram is connected from the app with `/telegram`; its token and paired accounts live in the Store (`core/integrations/`), not in `.env`.
- Never require the user to run shell commands for app features. Setup flows go through the daemon API so every client, including the web UI, can offer them.

## Backlog

Planned work lives in `BACKLOG.md`. Add new items there. When an item is finished, delete it and renumber the remaining codes in that category, including references to them.
