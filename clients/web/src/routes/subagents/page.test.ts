import { render } from "svelte/server";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { BackgroundSubagent, TaskSession } from "$lib/api/types";

function subagent(
  id: string,
  threadId: string,
  status: BackgroundSubagent["status"],
  fields: Partial<BackgroundSubagent> = {},
): BackgroundSubagent {
  return {
    id,
    user_id: "owner",
    thread_id: threadId,
    channel: "web",
    task: `Task ${id}\nwith details`,
    agent: "",
    plugins: [],
    started_at: "2026-11-01T10:00:00Z",
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

function codingSession(id: string, threadId: string, status: TaskSession["status"], fields: Partial<TaskSession> = {}): TaskSession {
  return {
    id,
    agent: "claude-code",
    name: "Claude Code",
    title: `Session ${id}`,
    repository: "/src/lo9i",
    status,
    started_at: "2026-11-01T11:00:00Z",
    step: "",
    waiting: 0,
    context_tokens: 0,
    context_limit: 0,
    model: "",
    thread_id: threadId,
    ...fields,
  };
}

const listed = vi.hoisted(() => ({ subagents: [] as BackgroundSubagent[], sessions: [] as TaskSession[] }));
// Each resource is what its loader returns from this client, at once.
const client = {
  subagents: { list: () => listed.subagents },
  tasks: { everywhere: () => listed.sessions, session: () => new Promise(() => {}) },
  mcp: { servers: () => [] },
  conversations: {
    list: () => [
      { thread_id: "t1", title: "Flights to Rome" },
      { thread_id: "t2", title: "Tax return" },
    ],
  },
};

vi.mock("$app/navigation", () => ({ goto: vi.fn() }));
vi.mock("$app/paths", () => ({ resolve: (path: string) => `/app${path}` }));
vi.mock("$app/state", () => ({ page: { url: new URL("http://localhost/app/subagents") } }));
vi.mock("$lib/daemon.svelte", () => ({
  resource: (load: (c: typeof client) => unknown) => ({ data: load(client) }),
  useDaemon: () => ({
    client,
    chats: { inboxId: "inbox" },
    hub: { on: () => () => {}, onReconnect: () => () => {} },
    notices: { report: vi.fn(), notify: vi.fn() },
  }),
}));

const { default: Page } = await import("./+page.svelte");

describe("Subagents page", () => {
  beforeEach(() => {
    listed.sessions = [];
  });

  it("lists every conversation's active subagents with their status, task and conversation", () => {
    listed.subagents = [
      subagent("a", "t1", "running", { step: "bash ls -la" }),
      subagent("b", "t2", "done", { ended_at: "2026-11-01T10:05:00Z" }),
      subagent("c", "inbox", "waiting"),
    ];
    const { body } = render(Page);
    expect(body).toContain("Task a</button>");
    expect(body).toContain("bash ls -la");
    expect(body).toContain("Flights to Rome");
    expect(body).toContain("The inbox");
    expect(body).toContain("Waiting for you");
    expect(body).not.toContain("with details</button>");
    expect(body).toMatch(/<input type="checkbox" checked[^>]*\/>\s*Active/);
    expect(body).not.toContain("Task b</button>");
    expect(body).not.toContain("Tax return");
  });

  it("says when none is active, and how to see those that ended", () => {
    listed.subagents = [subagent("b", "t2", "done", { ended_at: "2026-11-01T10:05:00Z" })];
    const { body } = render(Page);
    expect(body).toContain("Nothing active");
    expect(body).toContain("Turn off Active");
    expect(body).not.toContain("Task b</button>");
  });

  it("says when there are none yet", () => {
    listed.subagents = [];
    const { body } = render(Page);
    expect(body).toContain("None yet");
  });

  it("lists coding agents' sessions with the subagents, newest first, by their agent, title and folder", () => {
    listed.subagents = [subagent("a", "t1", "running")];
    listed.sessions = [
      codingSession("s1", "t2", "running", { step: "Bash: npm test" }),
      codingSession("s2", "t1", "done", { started_at: "2026-11-01T12:00:00Z" }),
    ];
    const { body } = render(Page);
    expect(body).toMatch(/Claude Code<\/span>Session s1<\/button>[\s\S]*Task a<\/button>/);
    expect(body).toContain("lo9i · Bash: npm test");
    expect(body).toContain("Tax return");
    // Only those working while Active is on.
    expect(body).not.toContain("Session s2");
    // The newest shows on the right, its work and a box to write to its agent.
    expect(body).toContain("Write to Claude Code");
  });

  it("isn't empty while only coding sessions are there", () => {
    listed.subagents = [];
    listed.sessions = [codingSession("s1", "t2", "done")];
    const { body } = render(Page);
    expect(body).not.toContain("None yet");
    expect(body).toContain("Nothing active");
  });
});
