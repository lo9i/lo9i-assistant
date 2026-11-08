import { describe, expect, it } from "vitest";
import { arcs, itemsOf, percent, strength } from "./contextParts";

describe("arcs", () => {
  it("puts the largest part first, each arc starting where the one before ends", () => {
    const parts = [
      { name: "Skills", tokens: 100, items: [] },
      { name: "Core tool definitions", tokens: 300, items: [] },
      { name: "Accounts", tokens: 0, items: [] },
      { name: "Profile", tokens: 100, items: [] },
    ];
    expect(arcs(parts, 10_000)).toEqual([
      { name: "Core tool definitions", tokens: 300, share: 0.03, start: 0, length: 0.6 },
      { name: "Skills", tokens: 100, share: 0.01, start: 0.6, length: 0.2 },
      { name: "Profile", tokens: 100, share: 0.01, start: 0.8, length: 0.2 },
    ]);
    expect(arcs(parts, 0)[0].share).toBe(0.6);
  });

  it("has no arcs without tokens", () => {
    expect(arcs([{ name: "Accounts", tokens: 0, items: [] }], 10_000)).toEqual([]);
  });
});

describe("percent", () => {
  it("rounds to a whole percent, keeping the decimals a small share needs", () => {
    expect(percent(0.426)).toBe("43%");
    expect(percent(0.004)).toBe("0.4%");
    expect(percent(0.0004)).toBe("0.04%");
    expect(percent(0.00001)).toBe("<0.01%");
  });
});

describe("strength", () => {
  it("fades from the largest to the smallest", () => {
    expect([0, 1, 2].map((r) => strength(r, 3))).toEqual([100, 50, 0]);
    expect(strength(0, 1)).toBe(100);
  });
});

describe("itemsOf", () => {
  it("lists what a part holds, largest first, each with its share of the window", () => {
    const facts = {
      name: "Saved facts",
      tokens: 100,
      items: [
        { name: "Likes jazz.", tokens: 20, detail: "", frame: false, fact_id: "a1", basic: true },
        { name: "", tokens: 5, detail: "", frame: true, fact_id: "", basic: false },
        { name: "Lives in Buenos Aires.", tokens: 75, detail: "", frame: false, fact_id: "b2", basic: true },
      ],
    };
    expect(itemsOf([facts], "Saved facts", 1000).map((i) => [i.name, i.share, i.scale])).toEqual([
      ["Lives in Buenos Aires.", 0.075, 1],
      ["Likes jazz.", 0.02, 20 / 75],
      ["", 0.005, 5 / 75],
    ]);
    expect(itemsOf([facts], "Skills", 1000)).toEqual([]);
  });
});
