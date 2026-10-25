// A list the daemon sends a page at a time (files, notifications), loaded as it's scrolled to its end.
import { DaemonUnavailableError } from "./api/errors";
import type { Page } from "./api/types";
import { describe } from "./notices";

/** How many items a page brings as the list is scrolled. */
export const PAGE_SIZE = 50;
/** The most the daemon sends in one page, for loading again what was shown. */
export const PAGE_MAX = 200;

export class PagedList<T> {
  items = $state.raw<T[]>([]);
  /** Whether the first page came. */
  loaded = $state(false);
  loading = $state(false);
  /** Whether the daemon has nothing after the items. */
  done = $state(false);
  error = $state<string | null>(null);
  // The end of the list is in sight: each page that comes brings the next, until the end leaves it.
  private nearEnd = false;
  // A page that failed stops loading more until the list is loaded again, so a daemon that can't be reached
  // isn't asked again and again.
  private stopped = false;
  private latest = 0;

  constructor(
    private readonly load: (page: Page) => Promise<T[]>,
    private readonly key: (item: T) => string,
    private readonly size = PAGE_SIZE,
  ) {}

  /** The first page again: what the list shows changed (a search). */
  restart = (): Promise<void> => this.fill(this.size);

  /** From the start again, as many as it shows, so it keeps its place: something in it changed. */
  reload = (): Promise<void> => this.fill(Math.max(this.size, this.items.length));

  /** The end of the list came in sight, or left it. */
  seen = (nearEnd: boolean): void => {
    this.nearEnd = nearEnd;
    if (nearEnd) void this.more();
  };

  /** The next page, unless one is loading or there's no more. */
  more = async (): Promise<void> => {
    if (!this.loaded || this.loading || this.done || this.stopped) return;
    const call = this.latest;
    this.loading = true;
    try {
      const page = await this.load({ offset: this.items.length, limit: this.size });
      if (call !== this.latest) return;
      this.show([...this.items, ...page], page.length < this.size);
    } catch (e) {
      if (call === this.latest) this.fail(e);
    } finally {
      if (call === this.latest) this.loading = false;
    }
    this.keepGoing(call);
  };

  /** The items from the start, `wanted` of them or all there are, in pages of at most PAGE_MAX, shown at once.
   * Only the newest load's answer is kept, so a slow earlier one can't overwrite it. */
  private async fill(wanted: number): Promise<void> {
    const call = ++this.latest;
    this.loading = true;
    try {
      const items = await this.from(0, wanted);
      if (call !== this.latest) return;
      this.stopped = false;
      this.show(items, items.length < wanted);
      this.loaded = true;
    } catch (e) {
      if (call === this.latest) this.fail(e);
    } finally {
      if (call === this.latest) this.loading = false;
    }
    this.keepGoing(call);
  }

  private async from(offset: number, wanted: number): Promise<T[]> {
    const limit = Math.min(wanted, PAGE_MAX);
    const page = await this.load({ offset, limit });
    return page.length < limit || wanted === limit ? page : [...page, ...(await this.from(offset + limit, wanted - limit))];
  }

  /** Each item once: one that came again in the next page (the list grew at its start meanwhile) is shown where
   * it came first. */
  private show(items: T[], done: boolean): void {
    const keys = new Set<string>();
    this.items = items.filter((item) => {
      const key = this.key(item);
      if (keys.has(key)) return false;
      keys.add(key);
      return true;
    });
    this.done = done;
    this.error = null;
  }

  /** A daemon that can't be reached isn't this list's error: the app says so for every page (ConnectionBanner), the
   * items stay, and the list is loaded again once it's back. */
  private fail(e: unknown): void {
    this.stopped = true;
    if (!(e instanceof DaemonUnavailableError)) this.error = describe(e);
  }

  /** The page that came still leaves the end in sight (a tall screen, a short page): the next one. */
  private keepGoing(call: number): void {
    if (call === this.latest && this.nearEnd) void this.more();
  }
}
