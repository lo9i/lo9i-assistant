import { render } from "svelte/server";
import { describe, expect, it, vi } from "vitest";
import type { ChatSnapshot } from "$lib/chat/controller";
import type { OpenChatsSnapshot } from "$lib/chat/openChats";
import { empty } from "$lib/chat/transcript";

const state = (threadId: string): ChatSnapshot => ({
  threadId,
  inboxId: "inbox",
  transcript: empty,
  busy: false,
  mirroring: false,
  approval: null,
  queued: [],
});
const quick = { subscribe: () => () => {}, getSnapshot: () => state("inbox") };
const daemon = vi.hoisted(() => ({ open: { chats: [], activeKey: null, moving: null } as OpenChatsSnapshot }));

vi.mock("$app/navigation", () => ({ goto: vi.fn() }));
vi.mock("$app/paths", () => ({ resolve: (path: string) => `/app${path}` }));
vi.mock("$app/state", () => ({ page: { url: new URL("http://localhost/app/conversations") } }));
vi.mock("$lib/daemon.svelte", () => ({
  resource: () => ({ data: [] }),
  external: (_subscribe: unknown, get: () => unknown) => ({ current: get() }),
  useDaemon: () => ({
    chats: { subscribe: () => () => {}, getSnapshot: () => daemon.open },
    voice: quick,
    text: quick,
  }),
}));

const { default: Sidebar } = await import("./Sidebar.svelte");

const closeButtons = (body: string) => body.match(/aria-label="Close [^"]*"/g) ?? [];

describe("Sidebar", () => {
  it("lets the last open conversation be closed too", () => {
    daemon.open = { chats: [{ key: "", state: state("t1") }], activeKey: "", moving: null };
    const { body } = render(Sidebar, { props: { name: "lo9i" } });
    expect(closeButtons(body)).toHaveLength(1);
  });

  it("lists nothing under Chat with none open", () => {
    daemon.open = { chats: [], activeKey: null, moving: null };
    const { body } = render(Sidebar, { props: { name: "lo9i" } });
    expect(body).not.toContain('class="open"');
    expect(closeButtons(body)).toEqual([]);
  });
});
