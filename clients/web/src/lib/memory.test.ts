import { describe, expect, it } from "vitest";
import { matching, sectionLabel } from "./memory";

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
