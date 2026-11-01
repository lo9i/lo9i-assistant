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
    result: "",
    waiting: [],
    ...fields,
  };
}

describe("SubagentsPanel", () => {
  it("shows a card for each with its task, status, what it's doing and for how long", () => {
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
    expect(body).toContain("RuntimeError: down");
    expect(body).toContain("lucide-loader-circle");
  });

  it("says when it's still thinking", () => {
    const { body } = render(SubagentsPanel, { props: { subagents: [subagent("a", "running")], onclose: () => {} } });
    expect(body).toContain("Thinking…");
  });
});
