import { describe, expect, it } from "vitest";
import { clock, phase } from "./voice";

const at = { recording: false, busy: false, preparingSpeech: false, speaking: false };

describe("phase", () => {
  it("follows the turn from listening to speaking", () => {
    expect(phase(at)).toBe("idle");
    expect(phase({ ...at, recording: true })).toBe("listening");
    expect(phase({ ...at, busy: true })).toBe("thinking");
    expect(phase({ ...at, preparingSpeech: true })).toBe("thinking");
    expect(phase({ ...at, speaking: true })).toBe("speaking");
  });
});

describe("clock", () => {
  it("shows minutes and seconds", () => {
    expect(clock(4200)).toBe("0:04");
    expect(clock(75000)).toBe("1:15");
  });
});
