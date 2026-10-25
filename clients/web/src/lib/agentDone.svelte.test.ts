import { afterEach, describe, expect, it, vi } from "vitest";
import { systemNotice } from "./agentDone.svelte";

/** A browser that grants notifications, with `Notification` as given. */
function browser(constructor: unknown): void {
  Object.assign(constructor as object, { permission: "granted" });
  vi.stubGlobal("Notification", constructor);
  vi.stubGlobal("window", { Notification: constructor, focus: () => {} });
}

describe("systemNotice", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("shows the browser's notification", () => {
    const shown = vi.fn();
    browser(
      class {
        constructor(title: string) {
          shown(title);
        }
      },
    );
    expect(systemNotice("Claude Code finished", "Done.", () => {})).toBe(true);
    expect(shown).toHaveBeenCalledWith("Claude Code finished");
  });

  it("says it can't where the permission is granted but the constructor throws, as on Android", () => {
    browser(
      class {
        constructor() {
          throw new TypeError("Illegal constructor");
        }
      },
    );
    expect(systemNotice("Claude Code finished", "Done.", () => {})).toBe(false);
  });
});
