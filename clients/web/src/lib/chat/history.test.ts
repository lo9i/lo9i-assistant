import { describe, expect, it } from "vitest";
import { onEdgeLine, sentTexts, step } from "./history";

describe("message history", () => {
  it("goes through the user's messages, oldest first, without repeats in a row", () => {
    const items = [
      { kind: "user", text: "hi" },
      { kind: "assistant", text: "hello" },
      { kind: "user", text: "hi" },
      { kind: "user", text: "  " },
      { kind: "user", text: "the weather?" },
    ];
    expect(sentTexts(items)).toEqual(["hi", "the weather?"]);
  });

  it("steps back with Up and forward with Down, past the newest to what was being typed", () => {
    expect(step(3, null, -1)).toBe(2);
    expect(step(3, 2, -1)).toBe(1);
    expect(step(3, 0, -1)).toBe(0);
    expect(step(3, 1, 1)).toBe(2);
    expect(step(3, 2, 1)).toBeNull();
    expect(step(3, null, 1)).toBeNull();
    expect(step(0, null, -1)).toBeNull();
  });

  it("acts only from the first line for Up and the last for Down", () => {
    expect(onEdgeLine("one\ntwo", 2, -1)).toBe(true);
    expect(onEdgeLine("one\ntwo", 5, -1)).toBe(false);
    expect(onEdgeLine("one\ntwo", 5, 1)).toBe(true);
    expect(onEdgeLine("one\ntwo", 2, 1)).toBe(false);
  });
});
