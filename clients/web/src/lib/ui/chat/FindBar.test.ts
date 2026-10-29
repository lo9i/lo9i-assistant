import { render } from "svelte/server";
import { describe, expect, it } from "vitest";
import FindBar from "./FindBar.svelte";

describe("FindBar", () => {
  it("offers a box, previous, next and close, with nothing to step through before a query", () => {
    const { body } = render(FindBar, { props: { root: undefined, content: [], onclose: () => {} } });
    expect(body).toContain('aria-label="Find in conversation"');
    expect(body).toContain('role="search"');
    expect(body).toMatch(/aria-label="Previous match"[^>]*disabled/);
    expect(body).toMatch(/aria-label="Next match"[^>]*disabled/);
    expect(body).toContain('aria-label="Close"');
    expect(body).not.toContain("No results");
  });
});
