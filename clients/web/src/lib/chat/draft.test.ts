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
    (await load()).of("t").text = "half a thought";
    const reloaded = (await load()).of("t");
    expect(reloaded.text).toBe("half a thought");
    reloaded.text = "";
    expect((await load()).of("t").text).toBe("");
  });

  it("works without storage, for this page only", async () => {
    vi.stubGlobal("sessionStorage", undefined);
    const box = (await load()).of("t");
    box.text = "still here";
    expect(box.text).toBe("still here");
  });

  it("keeps one draft per conversation", async () => {
    const draft = await load();
    const file = new File(["x"], "a.png", { type: "image/png" });
    const a = draft.of("a");
    a.text = "for a";
    a.files = [file];
    const b = draft.of("b");
    expect(b.text).toBe("");
    expect(b.files).toEqual([]);
    b.text = "for b";
    expect(draft.of("a").text).toBe("for a");
    expect(draft.of("a").files).toEqual([file]);
    expect((await load()).of("b").text).toBe("for b");
  });

  it("shares a conversation's draft between its boxes, a card's and its pane's", async () => {
    const draft = await load();
    draft.of("a").text = "typed in the card";
    expect(draft.of("a").text).toBe("typed in the card");
  });
});
