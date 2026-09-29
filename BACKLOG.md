# Backlog

Open work, tackled one at a time. Finished items are deleted and the remaining codes renumbered.
A = action, G = memory gap, H = context improvement, Q = open question, R = risk.

## Owner's tasks

- A1. Test with a real Anthropic API key (also confirms caching via `cache_read_input_tokens`).
- A2. Strong Postgres password in `.env` (partly addresses R1).

## Next, in order

1. A3. FastAPI gateway + React UI (includes G3 once Q2 is answered).
2. A4. Worker (with G1, Q1 and spending limits). Sends notifications and approvals through Telegram.
3. G2. Memory search.
4. G4. Prune old checkpoints.

## Memory

- G1. Memory extraction runs in the same call as the epoch summary, which delays the reply that starts a new epoch. Move it to the worker (A4).
- G2. Facts and episodes are loaded up to the configured limits, with no search beyond them.
- G3. No way to view or edit memories (Q2).
- G4. Checkpoints are never pruned.

## Context

- H1. Better epoch summaries: quote user messages verbatim, keep ids and paths exactly, and add a `search_history` tool over the full checkpoint.
- H2. Replace old tool outputs within an epoch with short stubs.
- H3. Tell the digest to ignore instructions found in tool output, so injected text can't reach facts or the profile.

## Voice

- A5. Speech to text: transcribe voice messages (Telegram voice notes, UI microphone) before they reach the agent. Claude doesn't accept audio.
- A6. Text to speech: optional spoken replies (Telegram voice message, UI playback).
- A7. Real-time voice agent: live spoken conversation from the browser.
  - A speech-to-speech model (OpenAI GPT-Live) listens and speaks. No separate speech-to-text or text-to-speech step; transcripts come from the model's own events.
  - Audio goes directly between the browser and OpenAI over WebRTC. Our server only exchanges the connection offer and answer, and never handles audio.
  - A gateway process keeps a sideband WebSocket to OpenAI for each call. When the voice model needs to act, it calls a tool; the gateway forwards the call to `AssistantService` and returns the result, so Claude stays the brain and state stays in Postgres.
  - Tool calls are logged by the model's call id, so a retried call returns the first result.
  - Needs an OpenAI key in addition to the Anthropic key. Not needed for Telegram voice notes (A5, A6).

## Open questions and risks

- Q1. How the worker is triggered: schedule, queue, or polling.
- Q2. Memory management UI: view, edit, delete.
- R1. The agent can reach Postgres from bash. Use a strong password, or move bash to a sandbox container.
- Langfuse: run the self-hosted stack and set keys.
