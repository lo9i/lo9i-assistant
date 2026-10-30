import { render } from "svelte/server";
import { describe, expect, it } from "vitest";
import SectionEditor from "./SectionEditor.svelte";

const props = { plugins: ["calendar"], error: "", onsave: () => {}, onclose: () => {} };

describe("SectionEditor", () => {
  it("edits what a section shows and the plugins it reads", () => {
    const section = { id: "calendar", title: "Calendar", prompt: "Today's events.", plugins: ["calendar"], columns: 0, coded: false };
    const { body } = render(SectionEditor, { props: { ...props, section } });
    expect(body).toContain("<textarea");
    expect(body).toContain("Plugins it reads");
    expect(body).not.toContain("Built by lo9i's code");
  });

  it("says a section built by code is, and changes only its title and width", () => {
    const section = { id: "copilot", title: "Copilot", prompt: "The Copilot plan.", plugins: [], columns: 0, coded: true };
    const { body } = render(SectionEditor, { props: { ...props, section } });
    expect(body).toContain("Built by lo9i's code, not by the model: only its title and width can be changed here.");
    expect(body).toContain("The Copilot plan.");
    expect(body).not.toContain("<textarea");
    expect(body).not.toContain("Plugins it reads");
    expect(body).toContain('value="Copilot"');
    expect(body).toContain("Width");
  });
});
