import { render } from "svelte/server";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ConversationStats as Stats } from "$lib/api/types";
import ConversationStats from "./ConversationStats.svelte";

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
  context_tokens: 0,
  context_limit: 150000,
  context_agent: "",
  started_at: "2026-10-23T08:00:00Z",
  last_activity: "2026-10-23T09:00:00Z",
};

describe("ConversationStats", () => {
  beforeEach(() => {
    loaded.data = stats;
    loaded.error = null;
  });

  it("shows the conversation's line, with its figures in the tooltip", () => {
    const { body } = render(ConversationStats, { props: { threadId: "t1" } });
    expect(body).toContain("4 messages · 4.2k tokens · 2 tools");
    expect(body).toContain("Cache read tokens: 2,500");
  });

  it("shows a conversation with no messages yet", () => {
    loaded.data = { ...stats, messages: 0, input_tokens: 0, cache_read_tokens: 0, output_tokens: 0, tool_calls: 0 };
    expect(render(ConversationStats, { props: { threadId: "t1" } }).body).toContain("0 messages");
  });

  it("is hidden for another conversation's stats, or a failed load", () => {
    expect(render(ConversationStats, { props: { threadId: "t2" } }).body).not.toContain("messages");
    loaded.error = "Internal Server Error";
    const failed = render(ConversationStats, { props: { threadId: "t1" } }).body;
    expect(failed).not.toContain("tokens");
    expect(failed).not.toContain("Internal Server Error");
  });
});

describe("ConversationStats with little room", () => {
  it("has its figures with icons for their words, shown in the line's place where the status bar is narrow", () => {
    loaded.data = stats;
    loaded.error = null;
    const { body } = render(ConversationStats, { props: { threadId: "t1" } });
    expect(body).toContain("lucide-mail");
    expect(body).toContain("lucide-coins");
    expect(body).toContain("lucide-wrench");
    expect(body).toMatch(/lucide-wrench[\s\S]*?<\/svg>2</);
  });
});
