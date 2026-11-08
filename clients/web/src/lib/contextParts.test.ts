import { describe, expect, it } from "vitest";
import { arcs, percent, strength } from "./contextParts";

describe("arcs", () => {
  it("puts the largest part first, each arc starting where the one before ends", () => {
    const parts = [
      { name: "Skills", tokens: 100 },
      { name: "Core tool definitions", tokens: 300 },
      { name: "Accounts", tokens: 0 },
      { name: "Profile", tokens: 100 },
    ];
    expect(arcs(parts)).toEqual([
      { name: "Core tool definitions", tokens: 300, share: 0.6, start: 0, length: 0.6 },
      { name: "Skills", tokens: 100, share: 0.2, start: 0.6, length: 0.2 },
      { name: "Profile", tokens: 100, share: 0.2, start: 0.8, length: 0.2 },
    ]);
  });

  it("has no arcs without tokens", () => {
    expect(arcs([{ name: "Accounts", tokens: 0 }])).toEqual([]);
  });
});

describe("percent", () => {
  it("rounds to a whole percent, keeping a decimal for a part under one", () => {
    expect(percent(0.426)).toBe("43%");
    expect(percent(0.004)).toBe("0.4%");
  });
});

describe("strength", () => {
  it("fades from the largest to the smallest", () => {
    expect([0, 1, 2].map((r) => strength(r, 3))).toEqual([100, 50, 0]);
    expect(strength(0, 1)).toBe(100);
  });
});
