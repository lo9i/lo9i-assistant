// What every page uses to talk to the daemon, shared through Svelte context.
import { getContext, setContext } from "svelte";
import type { DaemonClient } from "./api/client";
import { DaemonUnavailableError } from "./api/errors";
import type { EventHub } from "./api/eventHub";
import type { ChatController } from "./chat/controller";
import type { OpenChats } from "./chat/openChats";
import { describe, type NoticeBoard } from "./notices";

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
  $effect(() => hub.on(kinds, () => loaded.reload()));
  $effect(() => hub.onReconnect(() => loaded.reload()));
  return loaded;
}

export class Resource<T> {
  data = $state<T>();
  error = $state<string | null>(null);
  private latest = 0;

  constructor(private readonly load: () => Promise<T>) {}

  /** Only the newest load's answer is kept, so a slow earlier one can't overwrite it. A daemon that can't be
   * reached isn't this data's error: the app says so for every page (ConnectionBanner), the data loaded before
   * stays, and it's loaded again once the daemon is back. */
  reload = (): void => {
    const call = ++this.latest;
    this.load().then(
      (data) => {
        if (call !== this.latest) return;
        this.data = data;
        this.error = null;
      },
      (e: unknown) => {
        if (call === this.latest && !(e instanceof DaemonUnavailableError)) this.error = describe(e);
      },
    );
  };
}

/** A value kept by a plain TypeScript object (subscribe + getSnapshot), as Svelte state. */
export function external<T>(subscribe: (listener: () => void) => () => void, get: () => T): { readonly current: T } {
  let current = $state(get());
  $effect(() => subscribe(() => (current = get())));
  return {
    get current() {
      return current;
    },
  };
}
