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
    expect([folderPanel.open, homePanel.open]).toEqual([true, false]);
    homePanel.toggle();
    expect(homePanel.open).toBe(true);
    expect(stored.get("lo9i.homePanel")).toBe("open");
    expect(stored.has("lo9i.folderPanel")).toBe(false);
  });

  it("keep what each was left at", async () => {
    const { folderPanel, homePanel } = await loaded({ "lo9i.folderPanel": "closed", "lo9i.homePanel": "open" });
    expect([folderPanel.open, homePanel.open]).toEqual([false, true]);
  });

  it("start hidden on a narrow screen", async () => {
    const { folderPanel, homePanel } = await loaded({ "lo9i.homePanel": "open" }, true);
    expect([folderPanel.open, homePanel.open]).toEqual([false, false]);
  });
});
