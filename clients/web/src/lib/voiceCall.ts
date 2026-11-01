// A live voice call's latest lines as the page shows them while the call is on, from the events OpenAI sends on the
// call's data channel (core/voice/). Pure, so the rules are testable without a call. The conversation keeps what's
// said too: the daemon writes each line there once it's said, so this shows only the latest few, as they're spoken.

export type CallLine = { id: string; who: "user" | "voice"; text: string; done: boolean };

export type CallTranscript = {
  lines: CallLine[];
  // The user is speaking, as the call's voice activity detection hears it.
  listening: boolean;
  // The voice asked the assistant, and waits for its answer.
  asking: boolean;
};

export const noLines: CallTranscript = { lines: [], listening: false, asking: false };

// Lines kept: what's older is in the conversation.
const KEPT = 6;

type CallEvent = {
  type?: string;
  item_id?: string;
  delta?: string;
  transcript?: string;
  item?: CallItem;
  response?: { output?: CallItem[] };
};
type CallItem = { id?: string; type?: string; role?: string };

/** The transcript after one of the call's events; events it doesn't show leave it as it is. */
export function heard(t: CallTranscript, event: CallEvent): CallTranscript {
  const id = event.item_id ?? "";
  switch (event.type) {
    case "input_audio_buffer.speech_started":
      return { ...t, listening: true };
    case "input_audio_buffer.speech_stopped":
      return { ...t, listening: false };
    // `conversation.item.created` is the name earlier versions of the API used.
    case "conversation.item.added":
    case "conversation.item.created":
      return added(t, event.item ?? {});
    case "conversation.item.input_audio_transcription.delta":
      return written(t, id, "user", (line) => ({ ...line, text: line.text + (event.delta ?? "") }));
    case "conversation.item.input_audio_transcription.completed":
      return written(t, id, "user", (line) => ({ ...line, text: event.transcript ?? line.text, done: true }));
    case "conversation.item.input_audio_transcription.failed":
      return written(t, id, "user", (line) => ({ ...line, done: true }));
    case "response.output_audio_transcript.delta":
      return written(t, id, "voice", (line) => ({ ...line, text: line.text + (event.delta ?? "") }));
    case "response.output_audio_transcript.done":
      return written(t, id, "voice", (line) => ({ ...line, text: event.transcript ?? line.text, done: true }));
    case "response.created":
      return { ...t, asking: false };
    case "response.done":
      return (event.response?.output ?? []).some((item) => item.type === "function_call") ? { ...t, asking: true } : t;
    default:
      return t;
  }
}

/** The lines to show: those with words, the latest last. */
export function shownLines(t: CallTranscript): CallLine[] {
  return t.lines.filter((line) => line.text.trim());
}

/** A message the user or the voice says takes its place in the order it was added, before its words come. */
function added(t: CallTranscript, item: CallItem): CallTranscript {
  const who: CallLine["who"] | null = item.role === "user" ? "user" : item.role === "assistant" ? "voice" : null;
  if (item.type !== "message" || who === null || !item.id || t.lines.some((line) => line.id === item.id)) return t;
  return { ...t, lines: [...t.lines, { id: item.id, who, text: "", done: false }].slice(-KEPT) };
}

function written(t: CallTranscript, id: string, who: CallLine["who"], change: (line: CallLine) => CallLine): CallTranscript {
  const known = t.lines.some((line) => line.id === id) ? t : added(t, { id, type: "message", role: who === "user" ? "user" : "assistant" });
  return { ...known, lines: known.lines.map((line) => (line.id === id ? change(line) : line)) };
}
