import { render } from "svelte/server";
import { describe, expect, it, vi } from "vitest";
import type { ChatItem } from "$lib/chat/transcript";
import Thread from "./Thread.svelte";

// Markdown is cleaned with the browser's DOM, which a server render hasn't got; the text is enough here.
vi.mock("$lib/markdown", () => ({ markdown: (text: string) => text }));

const reply: ChatItem = { kind: "assistant", id: 1, text: "Done." };
const routed: ChatItem = { kind: "assistant", id: 2, text: "→ Continued in “Trip”.", dispatchId: "d1" };
const props = { thinking: false, name: "lo9i", onsuggest: () => {} };

describe("Thread", () => {
  it("copies a reply from its corner, with no row of buttons under it", () => {
    const { body } = render(Thread, { props: { ...props, items: [reply] } });
    const bubble = body.slice(body.indexOf("assistant-bubble"), body.indexOf("Done."));
    expect(bubble).toContain('aria-label="Copy"');
    expect(body).not.toContain("message-footer");
  });

  it("keeps Move under a message the inbox sent on", () => {
    const { body } = render(Thread, { props: { ...props, items: [routed], onmove: () => {} } });
    expect(body).toContain('aria-label="Move"');
    expect(body).toContain("message-footer");
  });

  it("opens at the newest message with no Go to bottom link", () => {
    const { body } = render(Thread, { props: { ...props, items: [reply, routed] } });
    expect(body).not.toContain("Go to bottom");
  });

  it("shows a task for the agent collapsed under its name, apart from the user's messages", () => {
    const brief: ChatItem = { kind: "brief", id: 4, text: "Fix the failing tests", agent: "Claude Code" };
    const { body } = render(Thread, { props: { ...props, items: [brief, reply] } });
    expect(body).toContain("Task for Claude Code");
    expect(body).toContain('<details class="tool brief');
    expect(body).not.toContain("<details open");
    // Only a `.row.user` can be pinned over the thread.
    expect(body).not.toContain("row user");
    expect(body).not.toContain("user-bubble");
  });

  it("pins no message over a thread that hasn't scrolled", () => {
    const asked: ChatItem = { kind: "user", id: 3, text: "Plan the trip", files: [] };
    const { body } = render(Thread, { props: { ...props, items: [asked, reply] } });
    expect(body).toContain("Plan the trip");
    expect(body).not.toContain('class="asked');
  });
});
