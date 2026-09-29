# AGENTS.md

Personal AI assistant built on LangGraph. One core agent, several gateways (CLI, FastAPI + React UI, Telegram, worker loop), shared Postgres.

## Layout

```
src/assistant/
  core/          graph, llm, storage (Postgres), observability
    agent/       AssistantService facade + one mixin per concern
    conversation/  system prompt, epochs (compaction), digest, transcript, turn header
      prompts/   prompt texts, one .md file per prompt
    memory/      long-term memory in the Store: profile, facts, episodes
    tools/       self-registering tools
    web/         web search providers (SearXNG, Brave, DuckDuckGo), page fetching, URL safety, caching
  gateways/    cli/, api/, telegram/, worker/
ui/            React + Vite, talks only to gateways/api
```

## Architecture rules

- Dependencies point one way: gateways -> `core.agent` -> graph -> tools. Core never imports from gateways.
- Gateways use only `AssistantService`, `Session`, `MemorySnapshot` (`core/agent`), `Attachment` (`core/attachments.py`) and the event types in `core/events.py`. They don't touch the graph, checkpointer or store.
- Every gateway and the worker run as separate processes. Keep no state in process memory that another process needs. Shared state goes in Postgres.
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
- Run locally: `scripts/run.sh` (starts Ollama when `.env` points at it, Postgres, and the CLI).
- Telegram bot: `scripts/telegram.sh` (runs the bot container in the background and follows its logs).
- Postgres is on host port 5433.

## Backlog

Planned work lives in `BACKLOG.md`. Add new items there. When an item is finished, delete it and renumber the remaining codes in that category, including references to them.
