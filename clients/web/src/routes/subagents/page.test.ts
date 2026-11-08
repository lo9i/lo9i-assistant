import { render } from "svelte/server";
import { describe, expect, it, vi } from "vitest";
import type { BackgroundSubagent } from "$lib/api/types";

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

const listed = vi.hoisted(() => ({ subagents: [] as BackgroundSubagent[] }));
// Each resource is what its loader returns from this client, at once.
const client = {
  subagents: { list: () => listed.subagents },
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
    expect(body).toContain("No active subagents");
    expect(body).toContain("Turn off Active");
    expect(body).not.toContain("Task b</button>");
  });

  it("says when there are none yet", () => {
    listed.subagents = [];
    const { body } = render(Page);
    expect(body).toContain("None yet");
  });
});
