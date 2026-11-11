import { render } from "svelte/server";
import { describe, expect, it } from "vitest";
import type { TaskSession } from "$lib/api/types";
import TaskStatus from "./TaskStatus.svelte";

const session: TaskSession = {
  id: "s1",
  agent: "claude-code",
  name: "Claude Code",
  title: "Fix tests",
  repository: "/repo",
  status: "running",
  started_at: new Date(Date.now() - 5 * 60_000).toISOString(),
  step: "",
  waiting: 0,
  context_tokens: 50000,
  context_limit: 200000,
  model: "claude-opus-5-5",
  thread_id: "t1",
};

describe("TaskStatus", () => {
  it("shows its agent's context and model, and how long it's been at it, but not how it's doing", () => {
    const { body } = render(TaskStatus, { props: { session, ended: "" } });
    expect(body).not.toContain("working…");
    expect(body).toContain("Claude Code's context");
    expect(body).toContain("50k / 200k tokens");
    expect(body).toContain("claude-opus-5-5");
    expect(body).toContain("5 min");
  });

  it("leaves out what its worker doesn't say", () => {
    const { body } = render(TaskStatus, {
      props: { session: { ...session, status: "done", context_tokens: 0, context_limit: 0, model: "" }, ended: "" },
    });
    expect(body).not.toContain("done");
    expect(body).not.toContain("context");
    expect(body).not.toContain('class="model');
  });
});
