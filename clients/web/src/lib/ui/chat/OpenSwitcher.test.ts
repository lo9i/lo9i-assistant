import { render } from "svelte/server";
import { describe, expect, it, vi } from "vitest";
import type { ChatSnapshot } from "$lib/chat/controller";
import type { OpenChatsSnapshot } from "$lib/chat/openChats";
import { empty } from "$lib/chat/transcript";

const state = (threadId: string, approval: ChatSnapshot["approval"] = null): ChatSnapshot => ({
  threadId,
  inboxId: "inbox",
  transcript: empty,
  busy: false,
  mirroring: false,
  approval,
  queued: [],
});
const daemon = vi.hoisted(() => ({ open: { chats: [], activeKey: null, moving: null } as OpenChatsSnapshot }));

vi.mock("$app/navigation", () => ({ goto: vi.fn() }));
vi.mock("$app/paths", () => ({ resolve: (path: string) => `/app${path}` }));
vi.mock("$lib/daemon.svelte", () => ({
  resource: () => ({ data: [] }),
  external: (_subscribe: unknown, get: () => unknown) => ({ current: get() }),
  useDaemon: () => ({ chats: { subscribe: () => () => {}, getSnapshot: () => daemon.open } }),
}));

const { default: OpenSwitcher } = await import("./OpenSwitcher.svelte");

describe("OpenSwitcher", () => {
  it("counts the open conversations and says when one waits for an answer", () => {
    const asking = { interrupt_id: "i1", request: { tool: "bash" } } as unknown as ChatSnapshot["approval"];
    daemon.open = {
      chats: [
        { key: "a", state: state("t1") },
        { key: "b", state: state("t2", asking) },
        { key: "c", state: state("inbox") },
      ],
      activeKey: "a",
      moving: null,
    };
    const { body } = render(OpenSwitcher);
    expect(body).toContain('aria-label="Open conversations"');
    expect(body).toMatch(/class="count[^"]*">2</);
    expect(body).toContain('class="waiting');
  });

  it("shows nothing with none open", () => {
    daemon.open = { chats: [], activeKey: null, moving: null };
    expect(render(OpenSwitcher).body).not.toContain("<button");
  });
});
