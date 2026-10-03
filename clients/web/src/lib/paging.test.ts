import { describe, expect, it } from "vitest";
import { pageCount, pageOf } from "./paging";

describe("pageCount", () => {
  it("rounds up and is at least one", () => {
    expect(pageCount(0, 20)).toBe(1);
    expect(pageCount(20, 20)).toBe(1);
    expect(pageCount(21, 20)).toBe(2);
  });
});

describe("pageOf", () => {
  const items = Array.from({ length: 45 }, (_, i) => i);

  it("returns the items of the page", () => {
    expect(pageOf(items, 0, 20)).toEqual(items.slice(0, 20));
    expect(pageOf(items, 2, 20)).toEqual([40, 41, 42, 43, 44]);
  });

  it("clamps a page past the end to the last one", () => {
    expect(pageOf(items, 9, 20)).toEqual([40, 41, 42, 43, 44]);
    expect(pageOf([], 3, 20)).toEqual([]);
  });
});
