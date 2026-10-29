import { describe, expect, it } from "vitest";
import { counter, isFindKey, locate, nearest, onMac, step } from "./find";

const keys = { key: "f", metaKey: false, ctrlKey: false, altKey: false, shiftKey: false };

describe("isFindKey", () => {
  it("takes Cmd+F on a Mac and Ctrl+F elsewhere", () => {
    expect(isFindKey({ ...keys, metaKey: true }, true)).toBe(true);
    expect(isFindKey({ ...keys, ctrlKey: true }, false)).toBe(true);
    expect(isFindKey({ ...keys, key: "F", ctrlKey: true }, false)).toBe(true);
  });

  it("leaves other keys and the other system's modifier alone", () => {
    expect(isFindKey({ ...keys, ctrlKey: true }, true)).toBe(false);
    expect(isFindKey({ ...keys, metaKey: true }, false)).toBe(false);
    expect(isFindKey({ ...keys, metaKey: true, shiftKey: true }, true)).toBe(false);
    expect(isFindKey({ ...keys, key: "g", metaKey: true }, true)).toBe(false);
    expect(isFindKey(keys, true)).toBe(false);
  });

  it("knows Apple's systems by their platform", () => {
    expect(onMac("MacIntel")).toBe(true);
    expect(onMac("iPhone")).toBe(true);
    expect(onMac("Win32")).toBe(false);
    expect(onMac("Linux x86_64")).toBe(false);
  });
});

describe("locate", () => {
  it("finds every match, case aside", () => {
    expect(locate(["Rome, then rome again"], "ROME")).toEqual([
      { start: [0, 0], end: [0, 4] },
      { start: [0, 11], end: [0, 15] },
    ]);
  });

  it("finds a match across texts, ending in the text of its last letter", () => {
    // "the **trip** plan": the match starts in one text node and ends in the bold one.
    expect(locate(["the tr", "ip", " plan"], "trip")).toEqual([{ start: [0, 4], end: [1, 2] }]);
    expect(locate(["ab", "cd"], "b")).toEqual([{ start: [0, 1], end: [0, 2] }]);
  });

  it("takes the query as text, not a pattern", () => {
    expect(locate(["costs $5 (or more)"], "$5 (")).toEqual([{ start: [0, 6], end: [0, 10] }]);
    expect(locate(["a.b axb"], "a.b")).toHaveLength(1);
  });

  it("finds nothing for an empty query or none in the texts", () => {
    expect(locate(["anything"], "")).toEqual([]);
    expect(locate([], "x")).toEqual([]);
    expect(locate(["", "abc"], "abc")).toEqual([{ start: [1, 0], end: [1, 3] }]);
  });
});

describe("step", () => {
  it("goes round at either end", () => {
    expect(step(0, 3, 1)).toBe(1);
    expect(step(2, 3, 1)).toBe(0);
    expect(step(0, 3, -1)).toBe(2);
    expect(step(0, 0, 1)).toBe(-1);
  });
});

describe("nearest", () => {
  it("starts at the first match where the reader is, or the last one above", () => {
    expect(nearest([-300, -10, 40, 900], 0)).toBe(2);
    expect(nearest([-300, -10], 0)).toBe(1);
    expect(nearest([], 0)).toBe(-1);
  });
});

describe("counter", () => {
  it("says where the current match is among them", () => {
    expect(counter(0, 12, "rome")).toBe("1 of 12");
    expect(counter(-1, 0, "rome")).toBe("No results");
    expect(counter(-1, 0, "")).toBe("");
  });
});
