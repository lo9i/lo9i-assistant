import { describe, expect, it } from "vitest";
import { modelChoices } from "./models";

describe("modelChoices", () => {
  it("lists the main model first, once, by its listed name", () => {
    const offered = {
      main: "gpt-5",
      models: [
        { id: "claude-x", name: "Claude X" },
        { id: "gpt-5", name: "GPT-5" },
      ],
    };
    expect(modelChoices(offered)).toEqual([
      { id: "", name: "GPT-5" },
      { id: "claude-x", name: "Claude X" },
    ]);
  });

  it("names the main model by its id when the provider doesn't list it", () => {
    expect(modelChoices({ main: "local", models: [] })).toEqual([{ id: "", name: "local" }]);
  });
});
