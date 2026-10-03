import { describe, expect, it } from "vitest";
import { recordingFile, recordingType } from "./microphone.svelte";

describe("microphone", () => {
  it("records Opus where it can, else MP4", () => {
    expect(recordingType(() => true)).toBe("audio/webm;codecs=opus");
    expect(recordingType((t) => t === "audio/mp4")).toBe("audio/mp4");
    expect(recordingType(() => false)).toBe("");
  });

  it("names the file and drops codec parameters", () => {
    const at = new Date("2026-10-01T10:20:30Z");
    expect(recordingFile("audio/webm;codecs=opus", at)).toEqual({ name: "voice-2026-10-01-10-20-30.webm", type: "audio/webm" });
    expect(recordingFile("audio/mp4", at).name).toBe("voice-2026-10-01-10-20-30.m4a");
    expect(recordingFile("", at).type).toBe("audio/webm");
  });
});
