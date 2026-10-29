import { createRawSnippet } from "svelte";
import { render } from "svelte/server";
import { describe, expect, it } from "vitest";
import AgentStatus from "./AgentStatus.svelte";

const handoff = { server: "claude-code", command: "claude", name: "Claude Code", folder: "/repo" };

describe("AgentStatus", () => {
  it("names the agent, and its folder on hover, with no Interrupt button", () => {
    const { body } = render(AgentStatus, { props: { handoff, onback: () => {} } });
    expect(body).toMatch(/<span class="name[^"]*">Claude Code<\/span>/);
    expect(body).toContain('title="Claude Code in /repo"');
    expect(body).toContain("Back to the assistant");
    expect(body).not.toContain("Interrupt");
  });

  it("marks its name while it works", () => {
    const idle = render(AgentStatus, { props: { handoff, onback: () => {} } }).body;
    const working = render(AgentStatus, { props: { handoff, working: true, onback: () => {} } }).body;
    expect(idle).not.toMatch(/class="name[^"]*working/);
    expect(working).toMatch(/<span class="name[^"]*working[^"]*">Claude Code<\/span>/);
  });

  it("shows its context between its name and the way back", () => {
    const children = createRawSnippet(() => ({ render: () => "<span>fuel</span>" }));
    const { body } = render(AgentStatus, { props: { handoff, onback: () => {}, children } });
    const name = body.indexOf("Claude Code</span>");
    expect(name).toBeLessThan(body.indexOf("fuel"));
    expect(body.indexOf("fuel")).toBeLessThan(body.indexOf("Back to the assistant"));
  });
});
