import { render } from "svelte/server";
import { describe, expect, it, vi } from "vitest";
import type { RunningTask } from "$lib/api/types";
import WorkingStatus from "./WorkingStatus.svelte";

const running: RunningTask[] = [
  { id: "a1", agent: "Claude Code", thread_id: "t1", asked: "fix it", started_at: "2026-10-09T10:00:00Z", steps: ["Bash: pytest"] },
  { id: "b2", agent: "Copilot", thread_id: "t2", asked: "docs", started_at: "2026-10-09T10:00:00Z", steps: [] },
];

vi.mock("$lib/daemon.svelte", () => ({ resource: () => ({ data: running }) }));

describe("WorkingStatus", () => {
  it("says which agent works in this conversation, without its steps, which the thread shows", () => {
    const { body } = render(WorkingStatus, { props: { threadId: "t1" } });
    expect(body).toContain("Claude Code</strong> is working");
    expect(body).not.toContain("Copilot");
    expect(body).not.toContain("Bash: pytest");
  });
});
