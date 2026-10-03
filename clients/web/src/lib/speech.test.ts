import { describe, expect, it, vi } from "vitest";
import { addUser, apply, empty } from "./chat/transcript";
import { finalReply } from "./chat/transcript";
import { Player, speaksReply, speechParts } from "./speech";

describe("spoken replies", () => {
  it("speak when the setting says so", () => {
    expect(speaksReply("always", false)).toBe(true);
    expect(speaksReply("voice", true)).toBe(true);
    expect(speaksReply("voice", false)).toBe(false);
    expect(speaksReply("off", true)).toBe(false);
    expect(speaksReply(undefined, true)).toBe(false);
  });

  it("read only the answer after the last tool call", () => {
    let t = addUser(empty, "weather?", []);
    t = apply(t, { type: "TextDelta", text: "Let me check." });
    t = apply(t, { type: "ToolStarted", name: "web_search", args: {} });
    t = apply(t, { type: "TextDelta", text: "It's sunny." });
    expect(finalReply(t)).toBe("It's sunny.");
  });
});

describe("speaking part by part", () => {
  it("splits sentences, joins short ones and leaves code out", () => {
    const text = "Done. I sent the email to Ana with the report attached.\n\n```\nprint('x. y')\n```\nAnything else? Just say so!";
    expect(speechParts(text)).toEqual(["Done. I sent the email to Ana with the report attached.", "Anything else? Just say so!"]);
    expect(speechParts("")).toEqual([]);
  });

  it("plays the parts in order, preparing the next while one plays", async () => {
    const played: string[] = [];
    const asked: string[] = [];
    class FakeAudio {
      onended: (() => void) | null = null;
      onpause: (() => void) | null = null;
      constructor(private readonly url: string) {}
      play(): Promise<void> {
        played.push(this.url);
        queueMicrotask(() => this.onended?.());
        return Promise.resolve();
      }
      pause(): void {}
    }
    vi.stubGlobal("Audio", FakeAudio);
    vi.stubGlobal("URL", { createObjectURL: (b: Blob & { label?: string }) => b.label ?? "", revokeObjectURL: () => {} });
    let ended = 0;
    let started = 0;
    const player = new Player(() => ended++);
    const synthesize = (part: string) => {
      asked.push(part);
      return Promise.resolve(Object.assign(new Blob(), { label: part }));
    };
    // Each sentence is long enough to be a part of its own.
    const reply = "This is the first sentence of the reply, a long one. This is the second sentence of the reply.";
    await player.speak(reply, synthesize, () => started++);
    expect(played).toEqual(["This is the first sentence of the reply, a long one.", "This is the second sentence of the reply."]);
    expect(asked).toEqual(played);
    expect([started, ended]).toEqual([1, 1]);
    vi.unstubAllGlobals();
  });
});
