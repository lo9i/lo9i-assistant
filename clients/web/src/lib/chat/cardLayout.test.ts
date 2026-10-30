import { describe, expect, it } from "vitest";
import {
  beforeOf,
  besideOf,
  columnsOf,
  initial,
  MAX_PANES,
  MIN_WIDTH,
  movedCard,
  movedPane,
  ordered,
  parsed,
  replacedPane,
  resized,
  restored,
  serialized,
  toggledMax,
  unordered,
  withoutPane,
  withPane,
  type Layout,
} from "./cardLayout";

const panes = (...ids: string[]): Layout => ids.reduce((layout, id) => withPane(layout, id), initial);
const sum = (widths: number[]) => widths.reduce((a, b) => a + b, 0);

describe("card order", () => {
  it("is newest activity first until the user drags a card", () => {
    expect(ordered(["c", "b", "a"], null)).toEqual(["c", "b", "a"]);
  });

  it("keeps the order the user dragged, with conversations new since first and those gone left out", () => {
    expect(ordered(["d", "c", "b", "a"], ["a", "gone", "c", "b"])).toEqual(["d", "a", "c", "b"]);
  });

  it("moves a card before another, or to the end", () => {
    const shown = ["a", "b", "c", "d"];
    expect(movedCard(initial, shown, "d", "b").order).toEqual(["a", "d", "b", "c"]);
    expect(movedCard(initial, shown, "a", "c").order).toEqual(["b", "a", "c", "d"]);
    expect(movedCard(initial, shown, "b", null).order).toEqual(["a", "c", "d", "b"]);
    expect(movedCard(initial, shown, "b", "b").order).toEqual(["a", "c", "d", "b"]);
  });

  it("drops before the card pointed at, or after it past its middle", () => {
    expect(beforeOf(["a", "b", "c"], "b", false)).toBe("b");
    expect(beforeOf(["a", "b", "c"], "b", true)).toBe("c");
    expect(beforeOf(["a", "b", "c"], "c", true)).toBeNull();
  });

  it("goes back to newest first", () => {
    expect(unordered(movedCard(initial, ["a", "b"], "a", null)).order).toBeNull();
  });
});

describe("panes", () => {
  it("adds conversations side by side, each once, sharing the width evenly", () => {
    const layout = withPane(panes("a", "b"), "a");
    expect(layout.panes).toEqual(["b", "a"]);
    expect(layout.widths).toEqual([0.5, 0.5]);
    expect(panes("a", "b", "c").widths.map((w) => w.toFixed(3))).toEqual(["0.333", "0.333", "0.333"]);
  });

  it("adds one before another, the others keeping their proportions", () => {
    const wide = { ...panes("a", "b"), widths: [0.75, 0.25] };
    const layout = withPane(wide, "c", "b");
    expect(layout.panes).toEqual(["a", "c", "b"]);
    expect(layout.widths[0] / layout.widths[2]).toBeCloseTo(3);
    expect(layout.widths[1]).toBeCloseTo(1 / 3);
    expect(sum(layout.widths)).toBeCloseTo(1);
  });

  it(`keeps at most ${MAX_PANES}: the last gives way to a new one`, () => {
    expect(withPane(panes("a", "b", "c"), "d").panes).toEqual(["a", "b", "d"]);
    expect(withPane(panes("a", "b", "c"), "d", "a").panes).toEqual(["d", "a", "b"]);
    expect(withPane(panes("a", "b", "c"), "d").widths).toHaveLength(3);
  });

  it("closes one, the others sharing its width", () => {
    const layout = withoutPane({ ...panes("a", "b", "c"), widths: [0.5, 0.25, 0.25] }, "a");
    expect(layout.panes).toEqual(["b", "c"]);
    expect(layout.widths).toEqual([0.5, 0.5]);
    expect(withoutPane(layout, "gone")).toBe(layout);
  });

  it("moves one, keeping its width", () => {
    const layout = movedPane({ ...panes("a", "b", "c"), widths: [0.5, 0.3, 0.2] }, "c", "a");
    expect(layout.panes).toEqual(["c", "a", "b"]);
    expect(layout.widths.map((w) => w.toFixed(1))).toEqual(["0.2", "0.5", "0.3"]);
    expect(movedPane(layout, "c", null).panes).toEqual(["a", "b", "c"]);
  });

  it("shows another conversation in a pane's place and width", () => {
    const layout = replacedPane({ ...panes("a", "b"), widths: [0.7, 0.3] }, "a", "n");
    expect(layout.panes).toEqual(["n", "b"]);
    expect(layout.widths[0]).toBeCloseTo(0.7);
  });
});

describe("conversations beside the one shown", () => {
  it("shows the one shown alone until another opens beside it", () => {
    expect(columnsOf(initial, "a")).toEqual(["a"]);
    const two = besideOf(initial, "a", "b");
    expect(two.panes).toEqual(["a", "b"]);
    expect(columnsOf(two, "b")).toEqual(["a", "b"]);
  });

  it("adds to the columns the shown one is in, once, and never itself", () => {
    const two = besideOf(initial, "a", "b");
    expect(besideOf(two, "b", "c").panes).toEqual(["a", "b", "c"]);
    expect(besideOf(two, "a", "b")).toBe(two);
    expect(besideOf(two, "a", "a")).toBe(two);
  });

  it("starts new columns from one shown that isn't in them, keeping the old ones for when they're shown again", () => {
    const two = besideOf(initial, "a", "b");
    expect(columnsOf(two, "x")).toEqual(["x"]);
    expect(besideOf(two, "x", "y").panes).toEqual(["x", "y"]);
  });

  it(`keeps the one shown when there are ${MAX_PANES} already: the last other one gives way`, () => {
    const full = besideOf(besideOf(initial, "a", "b"), "a", "c");
    expect(besideOf(full, "c", "d").panes).toEqual(["a", "c", "d"]);
    expect(besideOf(full, "a", "d").panes).toEqual(["a", "b", "d"]);
  });
});

describe("resizing", () => {
  it("drags a divider, the two panes beside it sharing their width", () => {
    const widths = resized([0.4, 0.4, 0.2], 0, 0.1);
    expect(widths[0]).toBeCloseTo(0.5);
    expect(widths[1]).toBeCloseTo(0.3);
    expect(widths[2]).toBe(0.2);
  });

  it(`keeps each pane at least ${MIN_WIDTH} of the width`, () => {
    const close = (widths: number[], expected: number[]) => widths.forEach((w, i) => expect(w).toBeCloseTo(expected[i]));
    close(resized([0.5, 0.5], 0, 0.9), [1 - MIN_WIDTH, MIN_WIDTH]);
    close(resized([0.5, 0.5], 0, -0.9), [MIN_WIDTH, 1 - MIN_WIDTH]);
  });

  it("ignores a divider that isn't there", () => {
    expect(resized([1], 0, 0.1)).toEqual([1]);
  });
});

describe("full screen", () => {
  it("shows one full screen, and the layout again when pressed again or restored", () => {
    const max = toggledMax(panes("a"), "a");
    expect(max.maximized).toBe("a");
    expect(toggledMax(max, "a").maximized).toBeNull();
    expect(toggledMax(max, "b").maximized).toBe("b");
    expect(restored(max).maximized).toBeNull();
  });

  it("gives the layout back when the pane full screen closes", () => {
    expect(withoutPane(toggledMax(panes("a", "b"), "a"), "a").maximized).toBeNull();
    expect(withoutPane(toggledMax(panes("a", "b"), "a"), "b").maximized).toBe("a");
  });

  it("follows a pane shown full screen to the conversation it shows instead", () => {
    expect(replacedPane(toggledMax(panes("a"), "a"), "a", "n").maximized).toBe("n");
  });
});

describe("keeping the layout", () => {
  it("reads back what it kept, but the one full screen", () => {
    const layout: Layout = {
      view: "cards",
      order: ["b", "a"],
      panes: ["a", "b"],
      widths: [0.6, 0.4],
      maximized: "a",
    };
    expect(parsed(serialized(layout))).toEqual({ ...layout, maximized: null });
  });

  it("starts as a list with nothing kept, or what it kept is broken", () => {
    expect(parsed(null)).toEqual(initial);
    expect(parsed("{not json")).toEqual(initial);
    expect(parsed("[1]")).toEqual(initial);
  });

  it("keeps what it can of an odd record", () => {
    const layout = parsed(JSON.stringify({ view: "cards", order: [1], panes: ["a", "a", "b", "c", "d"], widths: [1] }));
    expect(layout.view).toBe("cards");
    expect(layout.order).toBeNull();
    expect(layout.panes).toEqual(["a", "b", "c"]);
    expect(layout.widths.map((w) => w.toFixed(3))).toEqual(["0.333", "0.333", "0.333"]);
  });
});
