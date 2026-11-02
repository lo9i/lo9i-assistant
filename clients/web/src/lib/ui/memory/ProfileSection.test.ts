import UserRound from "@lucide/svelte/icons/user-round";
import { render } from "svelte/server";
import { describe, expect, it } from "vitest";
import ProfileSection from "./ProfileSection.svelte";

const section = { name: "goals", items: ["run a marathon"], Icon: UserRound, onsave: async () => {} };

describe("ProfileSection", () => {
  it("has a drag handle that says how to move it, when it can be moved", () => {
    const { body } = render(ProfileSection, { props: { ...section, ongrab: () => {}, onstep: () => {} } });
    expect(body).toContain('title="Drag to reorder, or use the arrow keys"');
    expect(body).toContain('aria-label="Move Goals"');
    expect(body).toContain('data-section="goals"');
    expect(render(ProfileSection, { props: section }).body).not.toContain("Drag to reorder");
  });

  it("marks where a section dragged over it would go, and the one being dragged", () => {
    const { body } = render(ProfileSection, { props: { ...section, ongrab: () => {}, drop: "after", lifted: true } });
    expect(body).toMatch(/class="section surface--glass[^"]*lifted/);
    expect(body).toMatch(/class="section surface--glass[^"]*drop-after/);
  });
});
