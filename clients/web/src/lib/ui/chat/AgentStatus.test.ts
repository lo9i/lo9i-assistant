import { render } from "svelte/server";
import { describe, expect, it } from "vitest";
import AgentStatus from "./AgentStatus.svelte";

const handoff = { server: "claude-code", command: "claude", name: "Claude Code", folder: "/repo" };

describe("AgentStatus", () => {
  it("offers to interrupt the agent only while it works", () => {
    const working = render(AgentStatus, { props: { handoff, working: true, oninterrupt: () => {}, onback: () => {} } });
    expect(working.body).toContain("Interrupt");
    const idle = render(AgentStatus, { props: { handoff, working: false, oninterrupt: () => {}, onback: () => {} } });
    expect(idle.body).not.toContain("Interrupt");
  });
});
