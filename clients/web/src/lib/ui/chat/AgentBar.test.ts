import { render } from "svelte/server";
import { describe, expect, it } from "vitest";
import AgentBar from "./AgentBar.svelte";

const handoff = { server: "claude-code", command: "claude", name: "Claude Code", folder: "/repo" };

describe("AgentBar", () => {
  it("offers to interrupt the agent only while it works", () => {
    const working = render(AgentBar, { props: { handoff, working: true, oninterrupt: () => {}, onback: () => {} } });
    expect(working.body).toContain("Interrupt");
    const idle = render(AgentBar, { props: { handoff, working: false, oninterrupt: () => {}, onback: () => {} } });
    expect(idle.body).not.toContain("Interrupt");
  });
});
