import { describe, expect, it, vi } from "vitest";
import { DaemonUnavailableError } from "./api/errors";
import type { Page } from "./api/types";
import { PAGE_MAX, PagedList } from "./pagedList.svelte";

/** A daemon listing `total` numbered items, newest first, a page at a time. */
function daemon(total: number) {
  let items = Array.from({ length: total }, (_, i) => `item ${i}`);
  const load = vi.fn(async ({ offset, limit }: Page) => items.slice(offset, offset + limit));
  return { load, prepend: (item: string) => (items = [item, ...items]) };
}

const paged = (load: (page: Page) => Promise<string[]>, size = 2) => new PagedList(load, (item: string) => item, size);

describe("PagedList", () => {
  it("loads the first page, then the next ones as the end comes in sight, until there are no more", async () => {
    const { load } = daemon(5);
    const list = paged(load);
    await list.restart();
    expect(list.items).toEqual(["item 0", "item 1"]);
    expect([list.loaded, list.done]).toEqual([true, false]);
    await list.more();
    await list.more();
    expect(list.items).toHaveLength(5);
    expect(list.done).toBe(true);
    await list.more();
    expect(load).toHaveBeenCalledTimes(3);
  });

  it("keeps loading while the end stays in sight, and stops when it leaves", async () => {
    const { load } = daemon(9);
    const list = paged(load);
    await list.restart();
    list.seen(true);
    await vi.waitFor(() => expect(list.items).toHaveLength(9));
    expect(list.done).toBe(true);
    const more = paged(daemon(9).load);
    await more.restart();
    more.seen(true);
    more.seen(false);
    await vi.waitFor(() => expect(more.loading).toBe(false));
    expect(more.items).toHaveLength(4);
  });

  it("loads again from the start as many as it showed, in pages the daemon allows", async () => {
    const { load, prepend } = daemon(PAGE_MAX + 150);
    const list = paged(load, 100);
    await list.restart();
    for (let i = 0; i < 2; i++) await list.more();
    prepend("new");
    load.mockClear();
    await list.reload();
    expect(list.items[0]).toBe("new");
    expect(list.items).toHaveLength(300);
    expect(load.mock.calls.map(([page]) => page)).toEqual([
      { offset: 0, limit: PAGE_MAX },
      { offset: PAGE_MAX, limit: 100 },
    ]);
  });

  it("starts over from one page when what it lists changes", async () => {
    const { load } = daemon(9);
    const list = paged(load);
    await list.restart();
    await list.more();
    await list.restart();
    expect(list.items).toEqual(["item 0", "item 1"]);
  });

  it("shows an item that came again in the next page once, where it came first", async () => {
    const { load, prepend } = daemon(4);
    const list = paged(load);
    await list.restart();
    prepend("new");
    await list.more();
    expect(list.items).toEqual(["item 0", "item 1", "item 2"]);
  });

  it("keeps only the newest load's answer", async () => {
    let answer: (items: string[]) => void = () => {};
    const load = vi
      .fn<(page: Page) => Promise<string[]>>()
      .mockImplementationOnce(() => new Promise((resolve) => (answer = resolve)))
      .mockResolvedValueOnce(["fresh"]);
    const list = paged(load);
    const slow = list.restart();
    await list.restart();
    answer(["stale", "older"]);
    await slow;
    expect(list.items).toEqual(["fresh"]);
  });

  it("stops after a page fails until it's loaded again, and says why unless the daemon can't be reached", async () => {
    const { load } = daemon(9);
    const list = paged(load);
    await list.restart();
    load.mockRejectedValueOnce(new Error("Boom"));
    await list.more();
    expect(list.error).toContain("Boom");
    await list.more();
    expect(list.items).toHaveLength(2);
    await list.reload();
    expect(list.error).toBeNull();
    load.mockRejectedValueOnce(new DaemonUnavailableError("gone"));
    await list.more();
    expect(list.error).toBeNull();
    expect(list.items).toHaveLength(2);
  });
});
