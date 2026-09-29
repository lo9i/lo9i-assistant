# Backlog

Work items, tackled one at a time. Codes stay stable: A = action, G = memory gap, F = finding, Q = open question, R = risk.

## Done

- A3. Refactor code to the `AGENTS.md` rules.
- A4. `CLAUDE.md` imports `AGENTS.md`.
- G2. Attachments saved under `~/.lo9i/uploads`; checkpoints keep references, hydrated per model call.
- F1. Prompt caching enabled (top-level `cache_control`, 5-minute TTL).
- Service split into `core/agent/` mixins.

## Owner's tasks

- A1. Test with a real Anthropic API key (also confirms caching via `cache_read_input_tokens`).
- A2. Strong Postgres password in `.env` (partly addresses R1).

## Next, in order

1. G1. Compaction: summarize older turns past a size threshold. Also rebuild the system prompt at that point (F2) and add missing context (F3).
2. A5. Telegram gateway.
3. A6. FastAPI gateway + React UI (includes G5 once Q16 is answered).
4. A7. Worker (with G3, Q7 and spending limits).
5. G4. Memory search once memories exceed ~200.
6. G6. Prune old checkpoints.

## Memory

- G1. Conversations have no size cap. Cost grows every turn.
- G3. No background memory extraction (belongs in the worker).
- G4. All memories loaded (cap 200), no semantic search.
- G5. No way to view or edit memories (Q16).
- G6. Checkpoints are never pruned.
- G7. User profile: a structured document in the Store (wants, likes, dislikes, interests, technical level, projects, work), separate from flat memories. Updated by an `update_profile` tool and by G3, loaded at conversation start, editable in the UI (G5).

## Context and memory design (decided 2026-09-29)

Request order, stable to volatile: tools, system prompt (instructions, profile, facts, recent episodes), epoch summary, epoch messages. Each user message starts with a turn header: date, time and channel.

Memory types: profile (one structured Store record, G7), facts (Store records), episodes (Store record per finished epoch), working memory (checkpoint), files (disk).

- D1. Our own compaction. The conversation is split into epochs; state records where the current epoch starts. All messages stay in the checkpoint; only the current epoch is sent. At a new epoch: summarize the old one into an episode, rebuild the system prompt, start with the summary plus the last few turns.
- D2. A new epoch starts on a size limit (~150k tokens) or a time gap (~6 hours idle). Both configurable.
- D3. Background extraction (G3) runs when an epoch ends: updates profile and facts from the finished epoch, in the worker.
- D4. Turn header on every user message (date, time, channel).
- D5. Loading is configurable: the full profile always, max facts (default 200) and max episodes (default 5) as settings.

## Context sent to the model

- F2. The system prompt is never rebuilt in a long-lived conversation, so new memories and the profile don't appear until `/new`. Rebuild at compaction (G1).
- F3. The prompt lacks current date and time, channel, profile (G7), and summaries of past conversations.

## Voice

- A8. Speech to text: transcribe voice messages (Telegram voice notes, UI microphone) before they reach the agent. Claude doesn't accept audio.
- A9. Text to speech: optional spoken replies (Telegram voice message, UI playback).
- A10. Real-time voice agent: live spoken conversation from the browser.
  - A speech-to-speech model (OpenAI GPT-Live) listens and speaks. No separate speech-to-text or text-to-speech step; transcripts come from the model's own events.
  - Audio goes directly between the browser and OpenAI over WebRTC. Our server only exchanges the connection offer and answer, and never handles audio.
  - A gateway process keeps a sideband WebSocket to OpenAI for each call. When the voice model needs to act, it calls a tool; the gateway forwards the call to `AssistantService` and returns the result, so Claude stays the brain and state stays in Postgres.
  - Tool calls are logged by the model's call id, so a retried call returns the first result.
  - Needs an OpenAI key in addition to the Anthropic key. Not needed for Telegram voice notes (A8/A9).

## Open questions and risks

- Q7. How the worker is triggered: schedule, queue, or polling.
- Q16. Memory management UI: view, edit, delete.
- R1. The agent can reach Postgres from bash. Use a strong password, or move bash to a sandbox container.
- Langfuse: run the self-hosted stack and set keys.
