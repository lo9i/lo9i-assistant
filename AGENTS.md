# AGENTS.md

Personal AI assistant built on LangGraph. One core agent, several gateways (CLI, FastAPI + React UI, Telegram, worker loop), shared Postgres.

## Layout

```
src/assistant/
  core/        agent graph, tools, memory, service, observability
  gateways/    cli/, api/, telegram/, worker/
ui/            React + Vite, talks only to gateways/api
```

## Architecture rules

- Dependencies point one way: gateways -> `core.service` -> graph -> tools. Core never imports from gateways.
- Gateways use only `AssistantService`, `Session` (`core/service.py`), `Attachment` (`core/attachments.py`) and the event types in `core/events.py`. They don't touch the graph, checkpointer or store.
- Every gateway and the worker run as separate processes. Keep no state in process memory that another process needs. Shared state goes in Postgres.
- Never edit or delete past messages in a checkpoint. History is append-only.
- Messages use LangChain standard content blocks (`output_version="v1"` in `core/llm.py`). Code that reads messages uses standard block types, never provider-native ones.
- The system prompt and tool list stay byte-identical for the life of a conversation, so the prompt cache keeps hitting. The system prompt is built on the first turn and stored in graph state. Memory changes take effect in the next conversation.
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
- Type hints on all public signatures.
- Async all the way in core. No blocking I/O in async code.
- Match the style of surrounding code. Comments explain why, not what.

## Tooling

- Python 3.12, managed with `uv`. Add dependencies with `uv add`, never pip.
- Run locally: `docker compose run --rm cli`.
- Postgres is on host port 5433.
