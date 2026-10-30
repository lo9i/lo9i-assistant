import { describe, expect, it } from "vitest";
import {
  beforeOf,
  besideOf,
  columnsOf,
  docked,
  edgeOf,
  groupsOf,
  initial,
  MAX_PANES,
  MIN_SHARE,
  movedCard,
  ordered,
  parsed,
  rearranged,
  replacedPane,
  resized,
  resizedGroups,
  resizedWithin,
  restored,
  serialized,
  toggledMax,
  unordered,
  withoutPane,
  type Layout,
} from "./cardLayout";

/** Which conversations each group holds. */
const shape = (layout: Layout) => layout.groups.map((g) => g.ids);
const close = (shares: number[], expected: number[]) => {
  expect(shares).toHaveLength(expected.length);
  shares.forEach((s, i) => expect(s).toBeCloseTo(expected[i]));
};
// a and b side by side.
const two = docked(initial, "a", "b", "right");
// The page split in half, b and c stacked in the right half.
const three = docked(two, "b", "c", "bottom");

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

describe("conversations beside the one shown", () => {
  it("shows the one shown alone until another opens beside it", () => {
    expect(columnsOf(initial, "a")).toEqual(["a"]);
    const pair = besideOf(initial, "a", "b");
    expect([shape(pair), pair.arrange]).toEqual([[["a"], ["b"]], "side"]);
    expect(columnsOf(pair, "b")).toEqual(["a", "b"]);
  });

  it("adds a group after the others the one shown is with, once, and never itself", () => {
    const pair = besideOf(initial, "a", "b");
    expect(shape(besideOf(pair, "b", "c"))).toEqual([["a"], ["b"], ["c"]]);
    expect(besideOf(pair, "a", "b")).toBe(pair);
    expect(besideOf(pair, "a", "a")).toBe(pair);
  });

  it("starts anew from one shown that isn't with them, keeping the others for when they're shown again", () => {
    expect(columnsOf(three, "x")).toEqual(["x"]);
    expect(groupsOf(three, "x")).toEqual([{ ids: ["x"], shares: [1] }]);
    expect(groupsOf(three, "c")).toBe(three.groups);
    expect(shape(besideOf(three, "x", "y"))).toEqual([["x"], ["y"]]);
  });

  it(`keeps the one shown when there are ${MAX_PANES} already: the last other one gives way`, () => {
    const full = besideOf(besideOf(initial, "a", "b"), "a", "c");
    expect(shape(besideOf(full, "c", "d"))).toEqual([["a"], ["c"], ["d"]]);
    expect(shape(besideOf(full, "a", "d"))).toEqual([["a"], ["b"], ["d"]]);
  });
});

describe("dropping on a conversation", () => {
  const box = { left: 0, top: 0, width: 400, height: 800 };

  it("goes by the edge the pointer is nearest, measured against the conversation's size", () => {
    expect(edgeOf(box, 50, 400)).toBe("left");
    expect(edgeOf(box, 380, 400)).toBe("right");
    expect(edgeOf(box, 200, 60)).toBe("top");
    expect(edgeOf(box, 200, 760)).toBe("bottom");
  });

  it("stacks one dropped above or below the conversation shown alone", () => {
    const below = docked(initial, "a", "b", "bottom");
    expect([shape(below), below.arrange]).toEqual([[["a"], ["b"]], "stacked"]);
    expect(shape(docked(initial, "a", "b", "top"))).toEqual([["b"], ["a"]]);
  });

  it("puts one dropped at a side next to it, side by side", () => {
    const right = docked({ ...initial, arrange: "stacked" }, "a", "b", "right");
    expect([shape(right), right.arrange]).toEqual([[["a"], ["b"]], "side"]);
    expect(shape(docked(initial, "a", "b", "left"))).toEqual([["b"], ["a"]]);
  });

  it("splits a half in two: one dropped below a conversation side by side stacks in its half", () => {
    expect([shape(three), three.arrange]).toEqual([[["a"], ["b", "c"]], "side"]);
    close(three.shares, [0.5, 0.5]);
    close(three.groups[1].shares, [0.5, 0.5]);
  });

  it("splits a row in two: one dropped beside a conversation stacked shares its row", () => {
    const rows = docked(docked(initial, "a", "b", "bottom"), "b", "c", "right");
    expect([shape(rows), rows.arrange]).toEqual([[["a"], ["b", "c"]], "stacked"]);
  });

  it("gives a new group half of the room of the one it's dropped beside", () => {
    const beside = docked(two, "b", "c", "right");
    expect(shape(beside)).toEqual([["a"], ["b"], ["c"]]);
    close(beside.shares, [0.5, 0.25, 0.25]);
  });

  it("moves one already shown to where it's dropped", () => {
    expect(shape(docked(three, "a", "c", "left"))).toEqual([["c"], ["a"], ["b"]]);
    expect(shape(docked(three, "c", "b", "bottom"))).toEqual([["a"], ["c", "b"]]);
  });

  it(`keeps the one dropped on when there are ${MAX_PANES} already`, () => {
    expect(shape(docked(three, "a", "d", "bottom"))).toEqual([["a", "d"], ["b"]]);
  });

  it("leaves it alone dropped on itself", () => {
    expect(docked(initial, "a", "a", "top")).toBe(initial);
  });
});

describe("closing one", () => {
  it("gives its room to the others in its group", () => {
    const left = withoutPane(three, "c");
    expect([shape(left), left.arrange]).toEqual([[["a"], ["b"]], "side"]);
    close(left.shares, [0.5, 0.5]);
  });

  it("gives a group left empty's room to the others, two in one group then splitting the whole page", () => {
    const left = withoutPane(three, "a");
    expect([shape(left), left.arrange]).toEqual([[["b"], ["c"]], "stacked"]);
  });

  it("keeps nothing for one left alone, and leaves the layout as it is for one that isn't shown", () => {
    expect(shape(withoutPane(two, "a"))).toEqual([]);
    expect(withoutPane(three, "gone")).toBe(three);
  });

  it("shows another conversation in its place and share", () => {
    expect(shape(replacedPane(three, "c", "n"))).toEqual([["a"], ["b", "n"]]);
  });
});

describe("arranging", () => {
  it("places them side by side at first, turns columns into rows once asked, and back", () => {
    expect(initial.arrange).toBe("side");
    const rows = rearranged(three);
    expect([shape(rows), rows.arrange]).toEqual([shape(three), "stacked"]);
    expect(rearranged(rows).arrange).toBe("side");
  });

  it("reads an arrangement it doesn't know as side by side", () => {
    expect(parsed(JSON.stringify({ arrange: "diagonal" })).arrange).toBe("side");
  });
});

describe("resizing", () => {
  it("drags a divider, the two beside it sharing their room", () => {
    close(resized([0.4, 0.4, 0.2], 0, 0.1), [0.5, 0.3, 0.2]);
  });

  it(`keeps each at least ${MIN_SHARE} of the room`, () => {
    close(resized([0.5, 0.5], 0, 0.9), [1 - MIN_SHARE, MIN_SHARE]);
    close(resized([0.5, 0.5], 0, -0.9), [MIN_SHARE, 1 - MIN_SHARE]);
  });

  it("ignores a divider that isn't there", () => {
    expect(resized([1], 0, 0.1)).toEqual([1]);
  });

  it("resizes the groups, or the conversations within one", () => {
    close(resizedGroups(three, 0, 0.1).shares, [0.6, 0.4]);
    close(resizedWithin(three, 1, 0, -0.1).groups[1].shares, [0.4, 0.6]);
  });
});

describe("full screen", () => {
  it("shows one full screen, and the layout again when pressed again or restored", () => {
    const max = toggledMax(initial, "a");
    expect(max.maximized).toBe("a");
    expect(toggledMax(max, "a").maximized).toBeNull();
    expect(toggledMax(max, "b").maximized).toBe("b");
    expect(restored(max).maximized).toBeNull();
  });

  it("gives the layout back when the one full screen closes", () => {
    expect(withoutPane(toggledMax(three, "a"), "a").maximized).toBeNull();
    expect(withoutPane(toggledMax(three, "a"), "b").maximized).toBe("a");
  });

  it("follows the one full screen to the conversation it shows instead", () => {
    expect(replacedPane(toggledMax(three, "c"), "c", "n").maximized).toBe("n");
  });
});

describe("keeping the layout", () => {
  it("reads back what it kept, but the one full screen", () => {
    const layout: Layout = { ...resizedGroups(three, 0, 0.1), view: "cards", order: ["b", "a"], maximized: "a" };
    expect(parsed(serialized(layout))).toEqual({ ...layout, maximized: null });
  });

  it("starts as a list with nothing kept, or what it kept is broken", () => {
    expect(parsed(null)).toEqual(initial);
    expect(parsed("{not json")).toEqual(initial);
    expect(parsed("[1]")).toEqual(initial);
  });

  it("reads one kept before groups as each conversation a group of its own", () => {
    const layout = parsed(JSON.stringify({ view: "cards", order: [1], panes: ["a", "a", "b", "c", "d"], widths: [1] }));
    expect(layout.view).toBe("cards");
    expect(layout.order).toBeNull();
    expect(shape(layout)).toEqual([["a"], ["b"], ["c"]]);
    close(layout.shares, [1 / 3, 1 / 3, 1 / 3]);
    close(parsed(JSON.stringify({ panes: ["a", "b"], widths: [0.6, 0.4] })).shares, [0.6, 0.4]);
  });
});
