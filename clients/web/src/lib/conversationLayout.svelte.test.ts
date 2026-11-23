// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";

/** The conversations page's views mounted, in a browser that kept `kept`. Svelte is imported after the reset too,
 * so the component and the test share one runtime. */
async function mounted(kept: object) {
  const stored = new Map([["lo9i.conversationLayout", JSON.stringify(kept)]]);
  vi.stubGlobal("localStorage", {
    getItem: (key: string) => stored.get(key) ?? null,
    setItem: (key: string, value: string) => stored.set(key, value),
  });
  vi.resetModules();
  const { flushSync, mount, unmount } = await import("svelte");
  const { conversationLayout } = await import("./conversationLayout.svelte");
  const { default: Views } = await import("./ConversationLayoutViews.test.svelte");
  const app = mount(Views, { target: document.body });
  flushSync();
  return { conversationLayout, stored, flushSync, close: () => unmount(app) };
}

describe("conversation layout", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    document.body.innerHTML = "";
  });

  // A teardown reads state as it was before the change that tears it down: giving full screen back from it put the
  // cards back, so List did nothing.
  it("stays on the list when the cards view gives full screen back as it goes", async () => {
    const { conversationLayout, stored, flushSync, close } = await mounted({ view: "cards" });
    document.querySelector("button")?.click();
    flushSync();
    expect(conversationLayout.current.view).toBe("list");
    expect(document.body.textContent).toContain("list");
    expect(JSON.parse(stored.get("lo9i.conversationLayout") ?? "").view).toBe("list");
    close();
  });

  it("gives full screen back when the cards view goes", async () => {
    const { conversationLayout, flushSync, close } = await mounted({ view: "cards" });
    conversationLayout.change({ ...conversationLayout.current, maximized: "t1" });
    flushSync();
    document.querySelector("button")?.click();
    flushSync();
    expect(conversationLayout.current).toMatchObject({ view: "list", maximized: null });
    close();
  });
});
