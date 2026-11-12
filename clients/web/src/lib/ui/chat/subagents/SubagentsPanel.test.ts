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
    const { body } = render(SubagentsPanel, { props: { subagents, open: true, ontoggle: () => {} } });
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

  it("shows those that ended when none is at it, with the Active filter off", () => {
    const subagents = [subagent("c", "done", { ended_at: new Date().toISOString() })];
    const { body } = render(SubagentsPanel, { props: { subagents, open: true, ontoggle: () => {} } });
    expect(body).toContain("Task c</span>");
    expect(body).toContain("Answered: its answer went back to the conversation.");
    expect(body).toMatch(/<input type="checkbox"(?![^>]*checked)[^>]*\/>\s*Active/);
  });

  it("minimized, is a thin bar with a mark for each and how they're doing, and no cards", () => {
    const subagents = [subagent("a", "running"), subagent("b", "running"), subagent("c", "done", { ended_at: new Date().toISOString() })];
    const { body } = render(SubagentsPanel, { props: { subagents, open: false, ontoggle: () => {} } });
    expect(body).toMatch(/class="rail surface--glass status--running[^"]*"/);
    expect(body).toContain("Subagents · 2 working");
    expect(body.match(/class="mark mark--/g)).toHaveLength(3);
    expect(body).not.toContain("Task a</span>");
  });

  it("minimized, says when one waits for the user", () => {
    const { body } = render(SubagentsPanel, { props: { subagents: [subagent("a", "waiting")], open: false, ontoggle: () => {} } });
    expect(body).toMatch(/class="rail surface--glass status--waiting[^"]*"/);
    expect(body).toContain("Subagents · 1 waiting for you");
    expect(body).toContain("A subagent is waiting for your answer");
  });

  it("says when it's still thinking", () => {
    const { body } = render(SubagentsPanel, { props: { subagents: [subagent("a", "running")], open: true, ontoggle: () => {} } });
    expect(body).toContain("Thinking…");
  });
});
