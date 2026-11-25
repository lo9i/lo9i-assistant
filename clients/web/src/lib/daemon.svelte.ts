// What every page uses to talk to the daemon, shared through Svelte context.
import { getContext, setContext } from "svelte";
import type { DaemonClient } from "./api/client";
import { DaemonUnavailableError } from "./api/errors";
import type { EventHub } from "./api/eventHub";
import type { Page } from "./api/types";
import type { ChatController } from "./chat/controller";
import type { OpenChats } from "./chat/openChats";
import { describe, type NoticeBoard } from "./notices";
import { PagedList } from "./pagedList.svelte";

// `chats` are the conversations open in the chat; `voice` and `text` are the floating buttons', kept apart
// from them: each writes in the inbox and follows its message to where it was sent on.
export type Daemon = {
  client: DaemonClient;
  hub: EventHub;
  notices: NoticeBoard;
  chats: OpenChats;
  voice: ChatController;
  text: ChatController;
};

const KEY = Symbol("daemon");

export function provideDaemon(daemon: Daemon): void {
  setContext(KEY, daemon);
}

export function useDaemon(): Daemon {
  const daemon = getContext<Daemon | undefined>(KEY);
  if (daemon === undefined) throw new Error("useDaemon outside the app layout");
  return daemon;
}

/** Data loaded from the daemon, and loaded again whenever it reports a change of one of `kinds`,
 * or state that `load` reads (such as a selection) changes, and when the daemon can be reached again after it
 * couldn't, since changes made meanwhile weren't heard. Call during component setup. */
export function resource<T>(load: (client: DaemonClient) => Promise<T>, kinds: string[]): Resource<T> {
  const { client, hub } = useDaemon();
  const loaded = new Resource(() => load(client));
  $effect(() => loaded.reload());
  $effect(() => hub.on(kinds, () => loaded.refresh()));
  $effect(() => hub.onReconnect(() => loaded.refresh()));
  return loaded;
}

/** A list the daemon sends a page at a time, loaded as it's scrolled (PagedList, with ListEnd after its items): its
 * first page, and again when state that `load` reads (a search) changes; from the start, as much as it shows, when
 * the daemon reports a change of one of `kinds` and when it can be reached again. Call during component setup. */
export function pagedResource<T>(
  load: (client: DaemonClient, page: Page) => Promise<T[]>,
  key: (item: T) => string,
  kinds: string[],
): PagedList<T> {
  const { client, hub } = useDaemon();
  const list = new PagedList((page) => load(client, page), key);
  $effect(() => void list.restart());
  $effect(() => hub.on(kinds, () => void list.reload()));
  $effect(() => hub.onReconnect(() => void list.reload()));
  return list;
}

export class Resource<T> {
  data = $state<T>();
  error = $state<string | null>(null);
  private latest = 0;
  private loading = false;
  private again = false;

  constructor(private readonly load: () => Promise<T>) {}

  /** Loads now. Only the newest load's answer is kept, so a slow earlier one can't overwrite it: for when what `load`
   * asks for changed (a selection). A daemon that can't be reached isn't this data's error: the app says so for every
   * page (ConnectionBanner), the data loaded before stays, and it's loaded again once the daemon is back. */
  reload = (): void => {
    const call = ++this.latest;
    this.loading = true;
    this.load()
      .then(
        (data) => {
          if (call !== this.latest) return;
          this.data = data;
          this.error = null;
        },
        (e: unknown) => {
          if (call === this.latest && !(e instanceof DaemonUnavailableError)) this.error = describe(e);
        },
      )
      .finally(() => this.settled(call));
  };

  /** Loads again because the data changed: while a load is on its way, once more after it, however many changes come
   * meanwhile. A change heard on every step of busy work (a coding agent's) would otherwise start a load each time,
   * piling up past the browser's connections, each superseded by the next, so none would ever be shown. */
  refresh = (): void => {
    if (this.loading) this.again = true;
    else this.reload();
  };

  private settled(call: number): void {
    if (call !== this.latest) return;
    this.loading = false;
    if (!this.again) return;
    this.again = false;
    this.reload();
  }
}

/** A value kept by a plain TypeScript object (subscribe + getSnapshot), as Svelte state. Raw, not deeply reactive:
 * snapshots are never changed in place, and a new one keeps what didn't change (a transcript's items). Proxied, each
 * change would wrap the whole value again, so every message on the page would count as new and be rendered again. */
export function external<T>(subscribe: (listener: () => void) => () => void, get: () => T): { readonly current: T } {
  let current = $state.raw(get());
  $effect(() => subscribe(() => (current = get())));
  return {
    get current() {
      return current;
    },
  };
}
