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
});
