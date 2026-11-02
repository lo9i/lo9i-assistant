import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// A tab's storage, which a reload and a duplicated tab keep.
function storage(): Storage {
  const items = new Map<string, string>();
  return {
    getItem: (key) => items.get(key) ?? null,
    setItem: (key, value) => void items.set(key, value),
    removeItem: (key) => void items.delete(key),
    clear: () => items.clear(),
    key: () => null,
    get length() {
      return items.size;
    },
  };
}

async function loaded() {
  vi.resetModules();
  return (await import("./hiddenAsks.svelte")).hiddenAsks;
}

describe("hiddenAsks", () => {
  beforeEach(() => vi.stubGlobal("sessionStorage", storage()));
  afterEach(() => vi.unstubAllGlobals());

  it("keeps what the user hid hidden after a reload, until it's shown again", async () => {
    (await loaded()).hide("i1");
    const reloaded = await loaded();
    expect(reloaded.has("i1")).toBe(true);
    reloaded.show("i1");
    expect((await loaded()).has("i1")).toBe(false);
  });

  it("works for the page alone without storage", async () => {
    vi.stubGlobal("sessionStorage", undefined);
    const hidden = await loaded();
    hidden.hide("i1");
    expect(hidden.has("i1")).toBe(true);
  });
});
