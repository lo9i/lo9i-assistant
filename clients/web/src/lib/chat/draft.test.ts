import { beforeEach, describe, expect, it, vi } from "vitest";

function storage(): Storage {
  const items = new Map<string, string>();
  return {
    getItem: (k) => items.get(k) ?? null,
    setItem: (k, v) => void items.set(k, v),
    removeItem: (k) => void items.delete(k),
    clear: () => items.clear(),
    key: () => null,
    get length() {
      return items.size;
    },
  };
}

// A fresh module is a page load: the chat panel comes and goes, the module stays.
async function load() {
  vi.resetModules();
  return (await import("./draft.svelte")).draft;
}

describe("draft", () => {
  beforeEach(() => vi.stubGlobal("sessionStorage", storage()));

  it("keeps the text across a reload and forgets it once sent", async () => {
    (await load()).text = "half a thought";
    const reloaded = await load();
    expect(reloaded.text).toBe("half a thought");
    reloaded.text = "";
    expect((await load()).text).toBe("");
  });

  it("works without storage, for this page only", async () => {
    vi.stubGlobal("sessionStorage", undefined);
    const draft = await load();
    draft.text = "still here";
    expect(draft.text).toBe("still here");
  });
});
