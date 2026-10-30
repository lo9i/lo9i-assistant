import { render } from "svelte/server";
import { describe, expect, it } from "vitest";
import type { RunningTask } from "$lib/api/types";
import WorkingStatus from "./WorkingStatus.svelte";

const tasks: RunningTask[] = [
  { id: "a1", agent: "Claude Code", thread_id: "t1", asked: "fix it", started_at: "2026-10-09T10:00:00Z", steps: ["Bash: pytest"] },
];

describe("WorkingStatus", () => {
  it("says which agent works, without its steps, which the thread shows", () => {
    const { body } = render(WorkingStatus, { props: { tasks } });
    expect(body).toContain("Claude Code</strong> is working");
    expect(body).not.toContain("Bash: pytest");
  });

  it("shows nothing while none works", () => {
    expect(render(WorkingStatus, { props: { tasks: [] } }).body).not.toContain("is working");
  });
});
