import { describe, expect, it } from "vitest";
import { matching, placed, sectionLabel, stepped } from "./memory";

describe("sectionLabel", () => {
  it("reads like a heading", () => {
    expect(sectionLabel("about")).toBe("About");
    expect(sectionLabel("how_to_reply")).toBe("How to reply");
  });
});

describe("matching", () => {
  const items = [
    { id: "1", text: "Drives a red car", when: "" },
    { id: "2", text: "Likes jazz records", when: "" },
  ];
  it("keeps the items with every word, ignoring case", () => {
    expect(matching(items, "  RED car ").map((i) => i.id)).toEqual(["1"]);
    expect(matching(items, "red jazz")).toEqual([]);
    expect(matching(items, "")).toEqual(items);
  });
});

describe("placed and stepped", () => {
  const order = ["about", "people", "goals", "work"];

  it("puts a dragged section before or after the one it's dropped on", () => {
    expect(placed(order, "work", "about", false)).toEqual(["work", "about", "people", "goals"]);
    expect(placed(order, "about", "goals", true)).toEqual(["people", "goals", "about", "work"]);
    expect(placed(order, "people", "work", true)).toEqual(["about", "goals", "work", "people"]);
  });

  it("changes nothing dropped on itself or with a section that isn't there", () => {
    expect(placed(order, "goals", "goals", true)).toBe(order);
    expect(placed(order, "pets", "goals", true)).toBe(order);
    expect(placed(order, "goals", "pets", false)).toBe(order);
  });

  it("moves one place from the keyboard, and not past either end", () => {
    expect(stepped(order, "people", -1)).toEqual(["people", "about", "goals", "work"]);
    expect(stepped(order, "people", 1)).toEqual(["about", "goals", "people", "work"]);
    expect(stepped(order, "about", -1)).toBe(order);
    expect(stepped(order, "work", 1)).toBe(order);
  });
});
