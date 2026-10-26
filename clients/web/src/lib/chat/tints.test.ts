import { describe, expect, it } from "vitest";
import { assignTints } from "./tints";

describe("assignTints", () => {
  it("gives listed conversations different colours until every colour is in use", () => {
    const ids = ["a", "b", "c", "d", "e"];
    const picked = assignTints(ids, {}, 4);
    expect(new Set(ids.slice(0, 4).map((id) => picked[id])).size).toBe(4);
    // The fifth shares one: all four are taken.
    expect(picked.e).toBeLessThan(4);
  });

  it("keeps each one's colour while it's listed, and gives a new one a colour nobody listed has", () => {
    const kept = { a: 2, b: 0 };
    expect(assignTints(["a", "b", "c"], kept, 4)).toEqual({ a: 2, b: 0, c: 1 });
  });

  it("gives a conversation listed again its colour back, unless another listed one has it", () => {
    expect(assignTints(["x", "a"], { a: 3, x: 1 }, 4)).toEqual({ x: 1, a: 3 });
    // Both remember 1: the first listed keeps it, the other gets a free one.
    expect(assignTints(["x", "y"], { x: 1, y: 1 }, 4)).toEqual({ x: 1, y: 0 });
  });

  it("ignores a remembered colour that no longer exists", () => {
    expect(assignTints(["a"], { a: 9 }, 4)).toEqual({ a: 0 });
  });
});
