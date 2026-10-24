// The conversations this browser tab has open side by side, each a ChatController under a client id of
// its own, so the daemon keeps every one of them open and their replies run in parallel. One is shown at a
// time; the sidebar lists them all.
import type { Dispatched } from "../api/types";
import type { NoticeBoard } from "../notices";
import { ChatController, type ChatClient, type ChatSnapshot } from "./controller";

/** The client for an open conversation: `part` null for the first, the tab's own client id. */
export type ClientFor = (part: string | null) => ChatClient;

export type OpenChat = { key: string; chat: ChatController };

export type OpenChatsSnapshot = {
  chats: { key: string; state: ChatSnapshot }[];
  activeKey: string;
};

export class OpenChats {
  private readonly listeners = new Set<() => void>();
  private snapshot: OpenChatsSnapshot;
  private readonly unsubscribe = new Map<string, () => void>();

  private constructor(
    private readonly clientFor: ClientFor,
    private readonly channel: string,
    private readonly notices: NoticeBoard,
    private open: OpenChat[],
    private activeKey: string,
  ) {
    this.snapshot = this.build();
    open.forEach((o) => this.follow(o));
  }

  /** Reopens `threads`, the conversations open before a reload (the first under the tab's own client id),
   * showing the one at `active`. With none, opens the inbox. */
  static async open(clientFor: ClientFor, channel: string, threads: string[], active: number, notices: NoticeBoard): Promise<OpenChats> {
    const wanted = threads.length ? threads : [null];
    const opened = await Promise.all(
      wanted.map(async (threadId, i) => {
        const key = i === 0 ? "" : newKey();
        return { key, chat: await ChatController.open(clientFor(key || null), channel, threadId, notices) };
      }),
    );
    const open = withoutRepeats(opened);
    const shown = opened[active] && open.includes(opened[active]) ? opened[active] : open[0];
    return new OpenChats(clientFor, channel, notices, open, shown.key);
  }

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  getSnapshot = (): OpenChatsSnapshot => this.snapshot;

  /** The conversation shown. */
  get current(): ChatController {
    return (this.open.find((o) => o.key === this.activeKey) ?? this.open[0]).chat;
  }

  all(): ChatController[] {
    return this.open.map((o) => o.chat);
  }

  /** The conversations open, as their ids, and which one is shown; what a reload reopens. */
  saved(): { threads: string[]; active: number } {
    const threads = this.open.map((o) => o.chat.getSnapshot().threadId);
    return { threads, active: this.open.findIndex((o) => o.key === this.activeKey) };
  }

  activate(key: string): void {
    if (key === this.activeKey || !this.open.some((o) => o.key === key)) return;
    this.activeKey = key;
    this.changed();
  }

  /** Shows `threadId`: the open conversation that is on it, or opens it beside the others. */
  async show(threadId: string): Promise<void> {
    await this.shown(threadId);
  }

  private async shown(threadId: string): Promise<ChatController> {
    const open = this.open.find((o) => o.chat.getSnapshot().threadId === threadId);
    if (!open) return await this.add((client) => ChatController.open(client, this.channel, threadId, this.notices));
    this.activate(open.key);
    return open.chat;
  }

  /** The inbox sent a message on: where it went opens beside the others, or a new one, shown, and it's sent
   * there. The inbox stays open behind it, busy until the run there has started. */
  private async goOn(dispatched: Dispatched, started: () => void): Promise<void> {
    try {
      const chat = dispatched.thread_id ? await this.shown(dispatched.thread_id) : await this.startNew();
      await chat.sendDispatched(dispatched, started);
    } catch (e) {
      this.notices.report(e);
    }
  }

  /** Asks in the inbox where a message it sent on goes instead (the last one for ""), showing the inbox first;
   * it then goes on like any message the inbox sends on. */
  async move(dispatchId: string): Promise<void> {
    await this.goInbox();
    await this.current.move(dispatchId);
  }

  /** Writes `text` in the inbox, which sends it on to its conversation: the inbox is shown first, then where
   * the message went. */
  async write(text: string, files: File[]): Promise<void> {
    await this.goInbox();
    await this.current.send(text, files);
  }

  /** Opens a new conversation beside the others, shows it and returns it. */
  async startNew(): Promise<ChatController> {
    return await this.add((client) => ChatController.openNew(client, this.channel, this.notices));
  }

  /** Shows the inbox: the open conversation that is on it, or opens it beside the others, which stay open. */
  async goInbox(): Promise<void> {
    const inbox = this.open.find((o) => o.chat.getSnapshot().threadId === o.chat.getSnapshot().inboxId);
    if (inbox) return this.activate(inbox.key);
    await this.add((client) => ChatController.open(client, this.channel, null, this.notices));
  }

  /** Closes an open conversation; the last one stays. A reply still running keeps going in the daemon. */
  async close(key: string): Promise<void> {
    const index = this.open.findIndex((o) => o.key === key);
    if (index < 0 || this.open.length === 1) return;
    const [closed] = this.open.splice(index, 1);
    this.unsubscribe.get(key)?.();
    this.unsubscribe.delete(key);
    if (this.activeKey === key) this.activeKey = this.open[Math.min(index, this.open.length - 1)].key;
    this.changed();
    if (await closed.chat.leave()) this.notices.notify("Closed. Its reply keeps running; you'll find it in Chat.");
  }

  /** Stop showing every run; the daemon keeps them going. */
  closeAll(): void {
    this.open.forEach((o) => o.chat.close());
  }

  private async add(opening: (client: ChatClient) => Promise<ChatController>): Promise<ChatController> {
    const key = newKey();
    const chat = await opening(this.clientFor(key));
    const opened = { key, chat };
    this.open.push(opened);
    this.follow(opened);
    this.activeKey = key;
    this.changed();
    return chat;
  }

  private follow(open: OpenChat): void {
    open.chat.onDispatched = (dispatched, started) => this.goOn(dispatched, started);
    this.unsubscribe.set(
      open.key,
      open.chat.subscribe(() => this.changed()),
    );
  }

  private changed(): void {
    this.snapshot = this.build();
    this.listeners.forEach((listener) => listener());
  }

  private build(): OpenChatsSnapshot {
    return { chats: this.open.map((o) => ({ key: o.key, state: o.chat.getSnapshot() })), activeKey: this.activeKey };
  }
}

function newKey(): string {
  return crypto.randomUUID().slice(0, 8);
}

/** Two saved conversations can reopen as the same one (both gone, so both the inbox); the first stays. */
function withoutRepeats(opened: OpenChat[]): OpenChat[] {
  const seen = new Set<string>();
  return opened.filter((o) => {
    const threadId = o.chat.getSnapshot().threadId;
    if (seen.has(threadId)) {
      void o.chat.leave();
      return false;
    }
    seen.add(threadId);
    return true;
  });
}
