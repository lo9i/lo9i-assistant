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
    expect(body).toContain("Back to the assistant: its own model answers again, with its memory and tools (/claude off)");
    expect(body).toMatch(/<button[^>]*class="btn btn--ghost back[^"]*"[^>]*>.*lucide-undo-2.*Assistant<\/button>/s);
    expect(body).not.toContain("Interrupt");
  });

  it("shows its context between its name and the way back", () => {
    const children = createRawSnippet(() => ({ render: () => "<span>fuel</span>" }));
    const { body } = render(AgentStatus, { props: { handoff, onback: () => {}, children } });
    const name = body.indexOf("Claude Code</span>");
    expect(name).toBeLessThan(body.indexOf("fuel"));
    expect(body.indexOf("fuel")).toBeLessThan(body.indexOf("Back to the assistant"));
    expect(body.indexOf("fuel")).toBeLessThan(body.indexOf(">Assistant</button>"));
  });
});

describe("AgentStatus while its agent works", () => {
  it("says beside its name for how long, so the bar names it once", () => {
    const { body } = render(AgentStatus, { props: { handoff, onback: () => {}, since: "2026-10-09T10:00:00Z" } });
    expect(body).toMatch(/Claude Code<\/span>\s*<span class="working[^"]*">is working · /);
    expect(body).toContain("lucide-loader-circle");
    expect(body).not.toContain("lucide-bot");
  });

  it("shows only its name while it waits", () => {
    const { body } = render(AgentStatus, { props: { handoff, onback: () => {} } });
    expect(body).not.toContain("is working");
    expect(body).toContain("lucide-bot");
  });
});
