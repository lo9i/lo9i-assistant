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
    expect(body).toContain("30k / 120k tokens");
    expect(body).toContain("Older messages are summarized when it's full.");
    expect(body).toMatch(/<span class="percent[^"]*" style="color: var\(--color-accent\)">25%<\/span>/);
  });

  it("shows the agent's context while the conversation is handed to it", () => {
    loaded.data = { ...stats, context_tokens: 61000, context_limit: 200000, context_agent: "Claude Code" };
    const { body } = render(ContextFuel, { props: { threadId: "t1" } });
    expect(body).toContain("Claude Code's context");
    expect(body).toContain("61k / 200k tokens");
  });

  it("fades from the accent colour to yellow and then to red as it fills", () => {
    const at = (tokens: number) => {
      loaded.data = { ...stats, context_tokens: tokens, context_limit: 100000 };
      return render(ContextFuel, { props: { threadId: "t1" } }).body;
    };
    expect(at(50000)).toContain('style="color: var(--color-accent)"');
    expect(at(62500)).toContain('style="color: color-mix(in oklab, #e5b931 50%, var(--color-accent))"');
    expect(at(87500)).toContain('style="color: color-mix(in oklab, #e5534b 50%, #e5b931)"');
    expect(at(100000)).toContain('style="color: color-mix(in oklab, #e5534b 100%, #e5b931)"');
  });

  it("shows a dash, not 0%, before the agent says how full its context is, and is hidden for another conversation", () => {
    loaded.data = { ...stats, context_tokens: 0, context_limit: 0, context_agent: "Claude Code" };
    const { body } = render(ContextFuel, { props: { threadId: "t1" } });
    expect(body).toMatch(/<span class="percent[^"]*" style="[^"]*">–<\/span>/);
    expect(body).not.toContain("0%");
    expect(body).toContain('aria-label="Context not known yet"');
    expect(body).toContain("Not known until its first answer.");
    loaded.data = { ...stats, context_tokens: 0 };
    expect(render(ContextFuel, { props: { threadId: "t1" } }).body).not.toContain("0%");
    loaded.data = stats;
    expect(render(ContextFuel, { props: { threadId: "t2" } }).body).not.toContain("fuel");
  });
});

describe("ContextFuel with little room", () => {
  it("has a ring as full as the bar, which shows in its place where the status bar is narrow", () => {
    loaded.data = { ...stats, context_tokens: 50000, context_limit: 100000 };
    loaded.error = null;
    const { body } = render(ContextFuel, { props: { threadId: "t1" } });
    expect(body).toContain('class="ring');
    const circle = 2 * Math.PI * 6;
    expect(body).toContain(`stroke-dasharray="${0.5 * circle} ${circle}"`);
  });
});
