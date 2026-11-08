import { render } from "svelte/server";
import { describe, expect, it } from "vitest";
import SubagentStatus from "./SubagentStatus.svelte";

const status = {
  steps: 3,
  max_steps: 25,
  context_tokens: 30000,
  context_limit: 120000,
  started_at: new Date(Date.now() - 5 * 60_000).toISOString(),
  ended_at: "",
};

describe("SubagentStatus", () => {
  it("shows a delegate call's subagent's context, its model calls of the limit and how long it's been at it", () => {
    const { body } = render(SubagentStatus, { props: { status } });
    expect(body).toContain("Subagent's context");
    expect(body).toContain("30k / 120k tokens");
    expect(body).toMatch(/<span class="percent[^"]*" style="color: var\(--color-accent\)">25%<\/span>/);
    expect(body).toContain("3/25 model calls");
    expect(body).toContain("5 min");
  });

  it("shows only the count for one in the background, and its time only where asked", () => {
    const { body } = render(SubagentStatus, {
      props: { status: { ...status, steps: 1, max_steps: 0, context_tokens: 0 }, elapsed: false },
    });
    expect(body).toContain("1 model call<");
    expect(body).toContain("In the background it has no limit.");
    expect(body).toContain("Not known until its first answer.");
    expect(body).not.toContain("5 min");
  });
});
