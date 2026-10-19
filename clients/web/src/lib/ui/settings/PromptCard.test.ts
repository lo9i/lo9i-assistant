import { render } from "svelte/server";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { PromptSection } from "$lib/api/types";
import PromptCard from "./PromptCard.svelte";

const loaded = vi.hoisted(() => ({ data: [] as PromptSection[] }));

vi.mock("$lib/daemon.svelte", () => ({
  useDaemon: () => ({ client: {}, notices: {} }),
  resource: () => loaded,
}));

const persona = (text: string, problem = ""): PromptSection => ({
  name: "persona",
  title: "Persona",
  description: "Who it is.",
  text,
  default: "You are an assistant.",
  edited: true,
  problem,
});

const operating: PromptSection = {
  name: "operating",
  title: "Operating instructions",
  description: "How it works.",
  text: "Built in.",
  default: "Built in.",
  edited: false,
  problem: "",
};

describe("PromptCard", () => {
  beforeEach(() => {
    loaded.data = [persona("You are Lo9i."), operating];
  });

  it("shows the first section's text in the editor, marked as edited, with its reset", () => {
    const { body } = render(PromptCard);
    expect(body).toContain("Persona");
    expect(body).toContain("Operating instructions");
    expect(body).toContain("Who it is.");
    expect(body).toMatch(/<textarea[^>]*>You are Lo9i\.<\/textarea>/);
    expect(body).toContain("Edited");
    expect(body).toContain("Reset to default");
    expect(body).toMatch(/<button[^>]*disabled[^>]*>Save<\/button>/);
  });

  it("says why an edit can't be used, shows the built-in text and offers the reset", () => {
    loaded.data = [persona("You are an assistant.", "Can't read /home/u/.lo9i/SOUL.md: not UTF-8."), operating];
    const { body } = render(PromptCard);
    expect(body).toContain("read /home/u/.lo9i/SOUL.md: not UTF-8. The assistant uses the built-in text");
    expect(body).toMatch(/<textarea[^>]*>You are an assistant\.<\/textarea>/);
    expect(body).toContain("Reset to default");
  });
});
