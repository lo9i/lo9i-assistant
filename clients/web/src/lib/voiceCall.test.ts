import { describe, expect, it } from "vitest";
import { heard, noLines, shownLines, type CallTranscript } from "./voiceCall";

const play = (...events: object[]): CallTranscript => events.reduce<CallTranscript>(heard, noLines);
const user = (id: string) => ({ type: "conversation.item.added", item: { id, type: "message", role: "user" } });
const voice = (id: string) => ({ type: "conversation.item.added", item: { id, type: "message", role: "assistant" } });
const lines = (t: CallTranscript) => shownLines(t).map((line) => [line.who, line.text, line.done]);

describe("a call's lines", () => {
  it("show what's said as it's spoken, in the call's order", () => {
    const t = play(
      user("u1"),
      voice("v1"),
      { type: "response.output_audio_transcript.delta", item_id: "v1", delta: "Sure, " },
      // The user's words come after the voice started answering: their line keeps its place.
      { type: "conversation.item.input_audio_transcription.delta", item_id: "u1", delta: "what's " },
      { type: "conversation.item.input_audio_transcription.completed", item_id: "u1", transcript: "what's on today?" },
    );
    expect(lines(t)).toEqual([
      ["user", "what's on today?", true],
      ["voice", "Sure, ", false],
    ]);
    const done = heard(t, { type: "response.output_audio_transcript.done", item_id: "v1", transcript: "Sure, let me look." });
    expect(lines(done).at(-1)).toEqual(["voice", "Sure, let me look.", true]);
  });

  it("say when the user speaks and while the voice asks the assistant", () => {
    expect(play({ type: "input_audio_buffer.speech_started" }).listening).toBe(true);
    const asking = play({ type: "response.done", response: { output: [{ type: "function_call" }] } });
    expect(asking.asking).toBe(true);
    // The assistant answered: the voice speaks its answer in a new response.
    expect(heard(asking, { type: "response.created" }).asking).toBe(false);
  });

  it("keep only the latest lines, and leave out the ones without words", () => {
    const many = Array.from({ length: 9 }, (_, i) => [
      user(`u${i}`),
      { type: "conversation.item.input_audio_transcription.completed", item_id: `u${i}`, transcript: `line ${i}` },
    ]).flat();
    const t = play(...many, voice("v9"));
    expect(t.lines).toHaveLength(6);
    expect(lines(t).at(-1)).toEqual(["user", "line 8", true]);
  });

  it("ignore items that aren't the user's or the voice's words", () => {
    expect(play({ type: "conversation.item.added", item: { id: "f1", type: "function_call" } }).lines).toEqual([]);
    expect(play({ type: "session.updated" })).toEqual(noLines);
  });
});
