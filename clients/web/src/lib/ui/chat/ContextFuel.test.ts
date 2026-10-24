import { render } from "svelte/server";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ConversationStats as Stats } from "$lib/api/types";
import ContextFuel from "./ContextFuel.svelte";

const loaded: { data?: Stats; error: string | null } = { error: null };

vi.mock("$lib/daemon.svelte", () => ({ resource: () => loaded }));

const stats: Stats = {
  thread_id: "t1",
  messages: 4,
  model_calls: 3,
  input_tokens: 4000,
  cache_read_tokens: 2500,
  output_tokens: 200,
  tool_calls: 2,
  context_tokens: 30000,
  context_limit: 120000,
  context_agent: "",
  started_at: "2026-10-23T08:00:00Z",
  last_activity: "2026-10-23T09:00:00Z",
};

describe("ContextFuel", () => {
  beforeEach(() => {
    loaded.data = stats;
    loaded.error = null;
  });

  it("shows how full the assistant's context is", () => {
    const { body } = render(ContextFuel, { props: { threadId: "t1" } });
    expect(body).toContain("Context: 30k / 120k tokens (25%). Older messages are summarized when it's full.");
    expect(body).toMatch(/<span class="percent[^"]*">25%<\/span>/);
  });

  it("shows the agent's context while the conversation is handed to it", () => {
    loaded.data = { ...stats, context_tokens: 61000, context_limit: 200000, context_agent: "Claude Code" };
    const { body } = render(ContextFuel, { props: { threadId: "t1" } });
    expect(body).toContain("Claude Code's context: 61k / 200k tokens (31%), as of its last answer.");
  });

  it("is hidden before the agent's first answer and for another conversation", () => {
    loaded.data = { ...stats, context_tokens: 0, context_limit: 0, context_agent: "Claude Code" };
    expect(render(ContextFuel, { props: { threadId: "t1" } }).body).not.toContain("fuel");
    loaded.data = stats;
    expect(render(ContextFuel, { props: { threadId: "t2" } }).body).not.toContain("fuel");
  });
});
