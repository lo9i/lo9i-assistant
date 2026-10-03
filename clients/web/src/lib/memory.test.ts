import { describe, expect, it } from "vitest";
import { sectionLabel } from "./memory";

describe("sectionLabel", () => {
  it("reads like a heading", () => {
    expect(sectionLabel("about")).toBe("About");
    expect(sectionLabel("how_to_reply")).toBe("How to reply");
  });
});
