"""Live voice calls from the browser: a speech-to-speech model (OpenAI's Realtime API, realtime.py) listens and
speaks, and the assistant stays the brain.

The browser and OpenAI exchange the audio directly over WebRTC: the daemon only passes the browser's offer on and its
answer back (`OpenAIRealtime.call`), with the call's settings (session.py), and never handles audio. For each call it
keeps a sideband WebSocket to OpenAI (daemon/voice_calls.py). When the voice model needs to know or do something it
calls its one tool, ask_assistant, which the daemon runs through AssistantService as a run in the call's
conversation, so every app shows it; the tool's result is the assistant's reply (core/agent/voice_calls.py). Tool
calls are logged by the model's call id (tool_calls.py), so a call made again gets the first one's result.

What's said in the call is kept in its conversation as it's said (spoken.py), the user's words as the model's own
transcription heard them and the voice's as it spoke them (heard.py orders them), which history shows and no model
call sends; the assistant learns of them from the notes its requests come with (notes.py).

The voice needs an OpenAI key in addition to whatever the main model uses (key.py)."""
