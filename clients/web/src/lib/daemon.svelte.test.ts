import { describe, expect, it } from "vitest";
import { Resource } from "./daemon.svelte";

/** A load the test answers by hand, recording each one started. */
function loads(): { started: ((value: string) => void)[]; load: () => Promise<string> } {
  const started: ((value: string) => void)[] = [];
  return { started, load: () => new Promise<string>((resolve) => started.push(resolve)) };
}

const settle = () => new Promise((resolve) => setTimeout(resolve, 0));

describe("Resource", () => {
  it("refreshes one load at a time, once more after it however many changes came meanwhile", async () => {
    const { started, load } = loads();
    const loaded = new Resource(load);
    loaded.refresh();
    for (let i = 0; i < 50; i++) loaded.refresh();
    expect(started).toHaveLength(1);

    started[0]("first");
    await settle();
    expect(loaded.data).toBe("first");
    expect(started).toHaveLength(2);

    started[1]("second");
    await settle();
    expect(loaded.data).toBe("second");
    expect(started).toHaveLength(2);
  });

  it("shows each load refreshed while changes keep coming, never superseded by the next", async () => {
    const { started, load } = loads();
    const loaded = new Resource(load);
    loaded.refresh();
    for (let i = 0; i < 5; i++) {
      loaded.refresh();
      started[i](`load ${i}`);
      await settle();
      expect(loaded.data).toBe(`load ${i}`);
    }
  });

  it("reloads at once when what it asks for changed, keeping only the newest answer", async () => {
    const { started, load } = loads();
    const loaded = new Resource(load);
    loaded.reload();
    loaded.reload();
    expect(started).toHaveLength(2);
    started[1]("newest");
    started[0]("stale");
    await settle();
    expect(loaded.data).toBe("newest");
    expect(started).toHaveLength(2);
  });
});
