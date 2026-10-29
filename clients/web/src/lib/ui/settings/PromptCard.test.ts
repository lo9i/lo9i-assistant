import { render } from "svelte/server";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { PromptSection } from "$lib/api/types";
import PromptCard from "./PromptCard.svelte";

const loaded = vi.hoisted(() => ({ data: [] as PromptSection[] }));

vi.mock("$lib/daemon.svelte", () => ({
  useDaemon: () => ({ client: {}, notices: {} }),
  resource: () => loaded,
}));

const persona = (text: string, problem = "", built_in_changes = ""): PromptSection => ({
  name: "persona",
  title: "Persona",
  description: "Who it is.",
  text,
  default: "You are an assistant.",
  edited: true,
  problem,
  built_in_changes,
});

const operating: PromptSection = {
  name: "operating",
  title: "Operating instructions",
  description: "How it works.",
  text: "Built in.",
  default: "Built in.",
  edited: false,
  problem: "",
  built_in_changes: "",
};

describe("PromptCard", () => {
  beforeEach(() => {
    loaded.data = [persona("You are Lo9i."), operating];
  });

  it("shows a section it doesn't know with the daemon's description", () => {
    loaded.data = [{ ...operating, name: "other", title: "Other", description: "Something new." }];
    const { body } = render(PromptCard);
    expect(body).toContain("Other");
    expect(body).toContain("Something new.");
  });

  it("shows the first section's text in the editor, marked as edited, with its reset", () => {
    const { body } = render(PromptCard);
    expect(body).toContain("Persona");
    expect(body).toContain("Operating instructions");
    // The daemon's sections it knows are described in the language shown.
    expect(body).toContain("Who the assistant is and how it behaves.");
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

  it("says how the built-in text changed since the edit, and offers keeping the edit", () => {
    loaded.data = [persona("You are Lo9i.", "", "--- when you edited it\n+++ now\n+Be kind."), operating];
    const { body } = render(PromptCard);
    expect(body).toContain("The built-in text changed since you edited it.");
    expect(body).toContain("+Be kind.");
    expect(body).toContain("Keep my edit");
    loaded.data = [persona("You are Lo9i."), operating];
    expect(render(PromptCard).body).not.toContain("Keep my edit");
  });
});
