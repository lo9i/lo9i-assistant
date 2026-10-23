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
  it("says which conversation another task is in, and opens it", () => {
    const { body } = render(TasksBar, { props: { threadId: "t1", onopen: () => {} } });
    expect(body).toContain("in Docs");
    expect(body.match(/>Open</g)).toHaveLength(1);
  });

  it("shows another conversation's task with its latest step, and leaves this one's to the status bar", () => {
    const here = render(TasksBar, { props: { threadId: "t1", onopen: () => {} } }).body;
    expect(here).not.toContain("Bash: pytest");
    expect(here.match(/is working/g)).toHaveLength(1);
    const elsewhere = render(TasksBar, { props: { threadId: "t2", onopen: () => {} } }).body;
    expect(elsewhere).toContain("Bash: pytest");
    expect(elsewhere).not.toContain("Read: README.md");
  });
});
