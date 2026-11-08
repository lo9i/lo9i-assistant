import { render } from "svelte/server";
import { describe, expect, it } from "vitest";
import type { BackgroundSubagent } from "$lib/api/types";
import SubagentsPanel from "./SubagentsPanel.svelte";

function subagent(id: string, status: BackgroundSubagent["status"], fields: Partial<BackgroundSubagent> = {}): BackgroundSubagent {
  return {
    id,
    user_id: "owner",
    thread_id: "t1",
    channel: "web",
    task: `Task ${id}\nwith details`,
    agent: "",
    plugins: [],
    started_at: new Date(Date.now() - 5 * 60_000).toISOString(),
    status,
    ended_at: "",
    step: "",
    steps: 0,
    model_calls: 0,
    context_tokens: 0,
    context_limit: 0,
    result: "",
    waiting: [],
    ...fields,
  };
}

describe("SubagentsPanel", () => {
  it("shows a card for each active one with its task, status, what it's doing and for how long", () => {
    const subagents = [
      subagent("a", "running", { step: "bash ls -la" }),
      subagent("b", "waiting"),
      subagent("c", "failed", { result: "RuntimeError: down", ended_at: new Date().toISOString() }),
    ];
    const { body } = render(SubagentsPanel, { props: { subagents, onclose: () => {} } });
    expect(body).toContain("Task a</span>");
    expect(body).not.toContain("with details</span>");
    expect(body).toMatch(/class="card status--running[^"]*"/);
    expect(body).toContain("bash ls -la");
    expect(body).toContain("5 min");
    expect(body).toContain("Waiting for your answer");
    expect(body).toContain("lucide-loader-circle");
    expect(body).toMatch(/<input type="checkbox" checked[^>]*\/>\s*Active/);
    expect(body).not.toContain("Task c</span>");
    expect(body).not.toContain("RuntimeError: down");
  });

  it("says when none is active, and how to see those that ended", () => {
    const subagents = [subagent("c", "done", { ended_at: new Date().toISOString() })];
    const { body } = render(SubagentsPanel, { props: { subagents, onclose: () => {} } });
    expect(body).toContain("No active subagents.");
    expect(body).toContain("Turn off Active");
    expect(body).not.toContain("Task c</span>");
  });

  it("says when it's still thinking", () => {
    const { body } = render(SubagentsPanel, { props: { subagents: [subagent("a", "running")], onclose: () => {} } });
    expect(body).toContain("Thinking…");
  });
});
