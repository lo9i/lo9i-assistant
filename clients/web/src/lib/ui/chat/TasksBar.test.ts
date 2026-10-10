import { render } from "svelte/server";
import { describe, expect, it, vi } from "vitest";
import type { Conversation, RunningTask } from "$lib/api/types";
import TasksBar from "./TasksBar.svelte";

const running: RunningTask[] = [
  {
    id: "a1",
    agent: "Claude Code",
    thread_id: "t1",
    asked: "fix the tests",
    started_at: "2026-10-09T10:00:00Z",
    steps: ["Read: README.md", "Bash: pytest"],
  },
  { id: "b2", agent: "Claude Code", thread_id: "t2", asked: "write docs", started_at: "2026-10-09T10:00:00Z", steps: [] },
];
const conversations = [{ thread_id: "t2", title: "Docs" }] as Conversation[];

vi.mock("$lib/daemon.svelte", () => ({
  useDaemon: () => ({ client: {} }),
  resource: (load: (c: unknown) => unknown) => {
    const tasks = { running: () => "tasks" };
    return { data: load({ tasks, conversations: { list: () => "conversations" } }) === "tasks" ? running : conversations };
  },
}));

describe("TasksBar", () => {
  it("shows each running task's latest step, and which conversation another one is in", () => {
    const { body } = render(TasksBar, { props: { threadId: "t1", onopen: () => {} } });
    expect(body).toContain("Bash: pytest");
    expect(body).not.toContain("Read: README.md");
    expect(body).toContain("in Docs");
    expect(body.match(/>Open</g)).toHaveLength(1);
  });
});
