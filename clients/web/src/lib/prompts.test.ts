import { describe, expect, it } from "vitest";
import type { PromptSection } from "./api/types";
import { canSave, draftOf, promptState } from "./prompts";

const section = (text: string, edited: boolean): PromptSection => ({
  name: "operating",
  title: "Operating instructions",
  description: "How it works.",
  text,
  default: "Built in.",
  edited,
  problem: "",
  built_in_changes: "",
});

describe("prompt drafts", () => {
  it("shows the text in use until the user types", () => {
    expect(draftOf(section("Built in.", false), {})).toBe("Built in.");
    expect(draftOf(section("Built in.", false), { operating: "Mine." })).toBe("Mine.");
    expect(draftOf(section("Built in.", false), { persona: "Other." })).toBe("Built in.");
  });

  it("says whether the text is unsaved, the user's edit or the built-in one", () => {
    expect(promptState(section("Built in.", false), "Built in.")).toBe("built-in");
    expect(promptState(section("Mine.", true), "Mine.\n")).toBe("edited");
    expect(promptState(section("Mine.", true), "Mine, changed.")).toBe("unsaved");
  });

  it("saves only a changed text that isn't empty", () => {
    expect(canSave(section("Mine.", true), "Mine.")).toBe(false);
    expect(canSave(section("Mine.", true), "  ")).toBe(false);
    expect(canSave(section("Mine.", true), "Other.")).toBe(true);
  });
});
