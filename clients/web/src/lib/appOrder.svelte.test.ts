import { describe, expect, it } from "vitest";
import { appOrder } from "./appOrder.svelte";

const items = (...names: string[]) => names.map((name) => ({ name }));

describe("appOrder", () => {
  it("moves an app down and up, and sorts by it", () => {
    appOrder.move(["a", "b", "c"], "a", "c");
    expect(appOrder.sort(items("a", "b", "c")).map((i) => i.name)).toEqual(["b", "c", "a"]);
    appOrder.move(["b", "c", "a"], "a", "b");
    expect(appOrder.sort(items("a", "b", "c")).map((i) => i.name)).toEqual(["a", "b", "c"]);
  });

  it("puts apps never placed after the placed ones", () => {
    appOrder.move(["a", "b"], "b", "a");
    expect(appOrder.sort(items("a", "new", "b")).map((i) => i.name)).toEqual(["b", "a", "new"]);
  });
});
