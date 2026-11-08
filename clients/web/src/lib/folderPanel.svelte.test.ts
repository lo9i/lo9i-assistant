import { afterEach, describe, expect, it, vi } from "vitest";

/** The panels as a page loads them, in a browser `narrow` or not that kept `kept`. */
async function loaded(kept: Record<string, string>, narrow = false) {
  const stored = new Map(Object.entries(kept));
  vi.stubGlobal("window", { matchMedia: () => ({ matches: narrow }) });
  vi.stubGlobal("localStorage", {
    getItem: (key: string) => stored.get(key) ?? null,
    setItem: (key: string, value: string) => stored.set(key, value),
  });
  vi.resetModules();
  return { ...(await import("./folderPanel.svelte")), stored };
}

describe("folder panels", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("show the handed folder at first and the home folder only once asked", async () => {
    const { folderPanel, homePanel, stored } = await loaded({});
    expect([folderPanel.isOpen("a"), homePanel.isOpen("a")]).toEqual([true, false]);
    homePanel.toggle("a");
    expect(homePanel.isOpen("a")).toBe(true);
    expect(stored.get("lo9i.homePanel")).toBe("open");
    expect(stored.has("lo9i.folderPanel")).toBe(false);
  });

  it("keep what each was left at", async () => {
    const { folderPanel, homePanel } = await loaded({ "lo9i.folderPanel": "closed", "lo9i.homePanel": "open" });
    expect([folderPanel.isOpen("a"), homePanel.isOpen("a")]).toEqual([false, true]);
  });

  it("start hidden on a narrow screen", async () => {
    const { folderPanel, homePanel } = await loaded({ "lo9i.homePanel": "open" }, true);
    expect([folderPanel.isOpen("a"), homePanel.isOpen("a")]).toEqual([false, false]);
  });

  it("open beside one conversation only, the others shown as they were", async () => {
    const { homePanel } = await loaded({});
    homePanel.keep("a");
    homePanel.keep("b");
    homePanel.toggle("a");
    expect([homePanel.isOpen("a"), homePanel.isOpen("b")]).toEqual([true, false]);
  });

  it("show a conversation shown for the first time as the panel was last left", async () => {
    const { homePanel } = await loaded({});
    homePanel.keep("a");
    homePanel.toggle("a");
    expect(homePanel.isOpen("c")).toBe(true);
  });
});

describe("panels of work sent off", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("start minimized beside every conversation, even after one was opened", async () => {
    const { subagentsPanel, tasksPanel, stored } = await loaded({ "lo9i.subagentsPanel": "open", "lo9i.tasksPanel": "open" });
    expect([subagentsPanel.isOpen("a"), tasksPanel.isOpen("a")]).toEqual([false, false]);
    subagentsPanel.toggle("a");
    expect([subagentsPanel.isOpen("a"), subagentsPanel.isOpen("b")]).toEqual([true, false]);
    expect(JSON.parse(stored.get("lo9i.subagentsPanels") ?? "")).toEqual({ a: true });
  });

  it("keep what each conversation's was left at", async () => {
    const { subagentsPanel, tasksPanel } = await loaded({ "lo9i.tasksPanels": JSON.stringify({ a: true, b: false }) });
    expect([tasksPanel.isOpen("a"), tasksPanel.isOpen("b"), subagentsPanel.isOpen("a")]).toEqual([true, false, false]);
    tasksPanel.toggle("a");
    expect(tasksPanel.isOpen("a")).toBe(false);
  });

  it("forget the oldest conversations' past a few hundred", async () => {
    const { tasksPanel, stored } = await loaded({});
    for (let i = 0; i < 205; i++) tasksPanel.toggle(`c${i}`);
    const kept = Object.keys(JSON.parse(stored.get("lo9i.tasksPanels") ?? ""));
    expect([kept.length, kept[0], tasksPanel.isOpen("c204")]).toEqual([200, "c5", true]);
  });
});
