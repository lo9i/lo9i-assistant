// The voice button: tap to talk, tap to send, the reply is read aloud. What a tap does depends on
// the phase the turn is in.

export type Phase = "idle" | "listening" | "thinking" | "speaking";

export type TurnState = { recording: boolean; busy: boolean; preparingSpeech: boolean; speaking: boolean };

export function phase(state: TurnState): Phase {
  if (state.recording) return "listening";
  if (state.busy || state.preparingSpeech) return "thinking";
  return state.speaking ? "speaking" : "idle";
}

/** Recording time as "m:ss". */
export function clock(ms: number): string {
  const seconds = Math.max(0, Math.floor(ms / 1000));
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}
