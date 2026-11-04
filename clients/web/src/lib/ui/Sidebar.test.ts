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
const daemon = vi.hoisted(() => ({
  open: { chats: [], activeKey: null, moving: null } as OpenChatsSnapshot,
  // What each of the client's calls the sidebar loads answers, by "group.method"; [] for the rest.
  loaded: {} as Record<string, unknown>,
}));
// A client whose every call answers what `daemon.loaded` says for it.
const client = new Proxy(
  {},
  { get: (_, group) => new Proxy({}, { get: (_, method) => () => daemon.loaded[`${String(group)}.${String(method)}`] ?? [] }) },
);

vi.mock("$app/navigation", () => ({ goto: vi.fn() }));
vi.mock("$app/paths", () => ({ resolve: (path: string) => `/app${path}` }));
vi.mock("$app/state", () => ({ page: { url: new URL("http://localhost/app/conversations") } }));
vi.mock("$lib/daemon.svelte", () => ({
  resource: (load: (c: unknown) => unknown) => ({ data: load(client) }),
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

  it("links to the page of every conversation's subagents", () => {
    daemon.open = { chats: [], activeKey: null, moving: null };
    const { body } = render(Sidebar, { props: { name: "lo9i" } });
    expect(body).toContain('href="/app/subagents"');
  });

  it("offers an app's update on its icon, saying the versions", () => {
    daemon.open = { chats: [], activeKey: null, moving: null };
    daemon.loaded = {
      "mcp.servers": [{ name: "watchlist", page: true, enabled: true, icon: null }],
      "repositories.updates": [{ kind: "server", name: "watchlist", installed_version: "1.0.0", version: "1.1.0" }],
    };
    const { body } = render(Sidebar, { props: { name: "lo9i" } });
    expect(body).toContain('class="app-update');
    expect(body).toContain("Update available: 1.0.0 → 1.1.0. Click to update.");
  });

  it("shows the count an app's plugin gives beside it, labeled as the plugin says", () => {
    daemon.loaded = {
      "mcp.servers": [
        { name: "expenses", page: true, enabled: true, icon: null, badge: true },
        { name: "watchlist", page: true, enabled: true, icon: null, badge: false },
      ],
      "mcp.badges": { badges: [{ name: "expenses", count: 2, label: "2 bills due today" }], next_day_in: 3600 },
    };
    const { body } = render(Sidebar, { props: { name: "lo9i" } });
    expect(body.match(/class="badge[^"]*"/g)).toHaveLength(1);
    expect(body).toMatch(/aria-label="2 bills due today"[^>]*>2<\/span>/);
    expect(body).toContain('title="Expenses · 2 bills due today · ');
  });

  it("asks for no counts when no app's plugin counts anything", () => {
    daemon.loaded = {
      "mcp.servers": [{ name: "watchlist", page: true, enabled: true, icon: null, badge: false }],
      "mcp.badges": { badges: [{ name: "watchlist", count: 2, label: "" }], next_day_in: 3600 },
    };
    const { body } = render(Sidebar, { props: { name: "lo9i" } });
    expect(body).not.toContain('class="badge');
  });

  it("shows no update on an app that has none", () => {
    daemon.loaded = { "mcp.servers": [{ name: "watchlist", page: true, enabled: true, icon: null }] };
    const { body } = render(Sidebar, { props: { name: "lo9i" } });
    expect(body).toContain("Watchlist");
    expect(body).not.toContain("app-update");
  });
});
