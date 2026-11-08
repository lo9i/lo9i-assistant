import { afterEach, describe, expect, it, vi } from "vitest";

/** The widths as a page loads them, in a browser that kept `kept`. */
async function loaded(kept: string | null) {
  const stored = new Map<string, string>(kept === null ? [] : [["lo9i.panelWidths", kept]]);
  vi.stubGlobal("localStorage", {
    getItem: (key: string) => stored.get(key) ?? null,
    setItem: (key: string, value: string) => stored.set(key, value),
  });
  vi.resetModules();
  return { ...(await import("./panelWidths.svelte")), stored };
}

describe("panel widths", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("leave a panel its own width until it's dragged", async () => {
    const { panelWidth } = await loaded(null);
    expect(panelWidth("tasks")).toBeUndefined();
  });

  it("keep the share a panel was dragged to once the drag ends", async () => {
    const { panelWidths, panelWidth, stored } = await loaded(null);
    panelWidths.set("tasks", 0.4);
    expect(panelWidth("tasks")).toBe("40.00%");
    expect(stored.has("lo9i.panelWidths")).toBe(false);
    panelWidths.save();
    expect(JSON.parse(stored.get("lo9i.panelWidths") ?? "")).toEqual({ tasks: 0.4 });
  });

  it("come back after a reload, leaving out what isn't a share", async () => {
    const { panelWidth } = await loaded(JSON.stringify({ tasks: 0.35, folder: 4, "folder.file": "x" }));
    expect([panelWidth("tasks"), panelWidth("folder"), panelWidth("folder.file")]).toEqual(["35.00%", undefined, undefined]);
  });

  it("give a panel back its own width on reset, the others kept", async () => {
    const { panelWidths, panelWidth, stored } = await loaded(JSON.stringify({ tasks: 0.35, folder: 0.3 }));
    panelWidths.reset("tasks");
    expect([panelWidth("tasks"), panelWidth("folder")]).toEqual([undefined, "30.00%"]);
    expect(JSON.parse(stored.get("lo9i.panelWidths") ?? "")).toEqual({ folder: 0.3 });
  });

  it("start from nothing when what's kept can't be read", async () => {
    const { panelWidth } = await loaded("{not json");
    expect(panelWidth("tasks")).toBeUndefined();
  });
});
