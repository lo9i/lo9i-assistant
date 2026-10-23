import { render } from "svelte/server";
import { describe, expect, it } from "vitest";
import AgentStatus from "./AgentStatus.svelte";

const handoff = { server: "claude-code", command: "claude", name: "Claude Code", folder: "/repo" };

describe("AgentStatus", () => {
  it("names the agent and its folder, with no Interrupt button", () => {
    const { body } = render(AgentStatus, { props: { handoff, onback: () => {} } });
    expect(body).toContain("Claude Code</strong> in <code>/repo</code>");
    expect(body).toContain("Back to the assistant");
    expect(body).not.toContain("Interrupt");
  });
});
