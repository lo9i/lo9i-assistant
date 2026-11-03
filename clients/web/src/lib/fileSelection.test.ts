import { describe, expect, it } from "vitest";
import { pageWithFiles, stillShown, ticked, tickedAll } from "./fileSelection";

describe("file picks", () => {
  it("tick and untick a file, each once", () => {
    expect(ticked(["a"], "b", true)).toEqual(["a", "b"]);
    expect(ticked(["a", "b"], "b", true)).toEqual(["a", "b"]);
    expect(ticked(["a", "b"], "a", false)).toEqual(["b"]);
  });

  it("tick or untick the whole page, leaving picks not on it", () => {
    expect(tickedAll(["x", "a"], ["a", "b"], true)).toEqual(["x", "a", "b"]);
    expect(tickedAll(["x", "a", "b"], ["a", "b"], false)).toEqual(["x"]);
  });

  it("drop the files no longer shown", () => {
    expect(stillShown(["a", "gone"], ["a", "b"])).toEqual(["a"]);
  });
});

describe("pageWithFiles", () => {
  it("goes back to the last page there is", () => {
    expect(pageWithFiles(2, 100, 50)).toBe(1);
    expect(pageWithFiles(1, 0, 50)).toBe(0);
    expect(pageWithFiles(1, 51, 50)).toBe(1);
  });
});
