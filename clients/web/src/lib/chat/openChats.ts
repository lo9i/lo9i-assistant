// The conversations this browser tab has open side by side, each a ChatController under a client id of
// its own, so the daemon keeps every one of them open and their replies run in parallel. One is shown at a
// time; the sidebar lists them all. None of them is ever the inbox: it routes each message to its conversation
// (core/inbox.py) and isn't one to read, so Chat never shows it.
import { ApiError } from "../api/errors";
import type { ApprovalRequired, Decision, Dispatched } from "../api/types";
import { t } from "../i18n.svelte";
import type { NoticeBoard } from "../notices";
import { ChatController, type ChatClient, type ChatSnapshot } from "./controller";
import { ChatTab } from "./tab";

/** The client for an open conversation: `part` null for the first, the tab's own client id. */
export type ClientFor = (part: string | null) => ChatClient;

export type OpenChat = { key: string; chat: ChatController };

/** What showing a conversation did: shown, or nothing, for the inbox (Chat never shows it) or one that's gone. */
export type Shown = "shown" | "inbox" | "gone";

export type OpenChatsSnapshot = {
  chats: { key: string; state: ChatSnapshot }[];
  activeKey: string;
  // What the inbox asks while /move runs there (which conversation the message goes to instead).
  moving: ApprovalRequired | null;
};

export class OpenChats {
  private readonly listeners = new Set<() => void>();
  private snapshot: OpenChatsSnapshot;
  private readonly unsubscribe = new Map<string, () => void>();
  // The chat on the inbox a move runs in, kept out of the open ones for as long as it runs.
  private mover: ChatController | null = null;

  private constructor(
    private readonly clientFor: ClientFor,
    private readonly channel: string,
    private readonly notices: NoticeBoard,
    private readonly tab: ChatTab,
    private open: OpenChat[],
    private activeKey: string,
  ) {
    this.snapshot = this.build();
    open.forEach((o) => this.follow(o));
  }

  /** Reopens `threads`, the conversations open before a reload (the first under the tab's own client id),
   * showing the one at `active`. With none, opens a new one, as for one that's gone or was the inbox. Each is one
   * of `tab`'s chats. */
  static async open(
    clientFor: ClientFor,
    channel: string,
    threads: string[],
    active: number,
    notices: NoticeBoard,
    tab = new ChatTab(),
  ): Promise<OpenChats> {
    const wanted = threads.length ? threads : [null];
    const opened = await Promise.all(
      wanted.map(async (threadId, i) => {
        const key = i === 0 ? "" : newKey();
        return { key, chat: await ChatController.openInChat(clientFor(key || null), channel, threadId, notices, tab) };
      }),
    );
    const open = withoutRepeats(opened);
    const shown = opened[active] && open.includes(opened[active]) ? opened[active] : open[0];
    return new OpenChats(clientFor, channel, notices, tab, open, shown.key);
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

  /** The inbox's id, which no open conversation is on. */
  get inboxId(): string {
    return this.open[0].chat.getSnapshot().inboxId;
  }

  /** Shows `threadId`: the open conversation that is on it, or opens it beside the others; nothing for the inbox or
   * one that's gone. */
  async show(threadId: string): Promise<Shown> {
    if (threadId === this.inboxId) return "inbox";
    try {
      await this.shown(threadId);
      return "shown";
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) return "gone";
      throw e;
    }
  }

  /** Throws ApiError (404) for one that's gone. */
  private async shown(threadId: string): Promise<ChatController> {
    const open = this.open.find((o) => o.chat.getSnapshot().threadId === threadId);
    if (!open)
      return await this.add((client) => ChatController.openExisting(client, this.channel, threadId, this.inboxId, this.notices, this.tab));
    this.activate(open.key);
    return open.chat;
  }

  /** A fresh conversation's first message goes on in `threadId`: shows the other open one on it, if any, and closes
   * `from`, which nothing was written in. */
  private async routedTo(from: OpenChat, threadId: string): Promise<ChatController | null> {
    const there = this.open.find((o) => o !== from && o.chat.getSnapshot().threadId === threadId);
    if (!there) return null;
    this.activate(there.key);
    await this.close(from.key);
    return there.chat;
  }

  /** The inbox sent a message on: where it went opens beside the others, or a new one, shown, for the inbox to
   * send it there (null when it can't be opened). */
  private async whereSent(dispatched: Dispatched): Promise<ChatController | null> {
    try {
      return dispatched.thread_id ? await this.shown(dispatched.thread_id) : await this.startNew();
    } catch (e) {
      this.notices.report(e);
      return null;
    }
  }

  /** Asks in the inbox where a message it sent on goes instead (the last one for ""), from a chat on it that isn't
   * shown, whose question shows as `moving`; where it goes then opens like any message the inbox sends on. */
  async move(dispatchId: string): Promise<void> {
    if (this.mover !== null) return;
    const mover = await ChatController.open(this.clientFor(newKey()), this.channel, this.inboxId, this.notices, this.tab);
    this.mover = mover;
    mover.onDispatched = (dispatched) => this.whereSent(dispatched);
    const unsubscribe = mover.subscribe(() => this.changed());
    try {
      await mover.move(dispatchId);
    } finally {
      unsubscribe();
      this.mover = null;
      this.changed();
      await mover.leave();
    }
  }

  /** Answers what the inbox asks while a move runs there. */
  answerMove(decision: Decision): void {
    this.mover?.answer(decision);
  }

  /** Opens a new conversation beside the others, shows it and returns it. */
  async startNew(): Promise<ChatController> {
    return await this.add((client) => ChatController.openNew(client, this.channel, this.notices, this.tab));
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
    if (await closed.chat.leave()) this.notices.notify(t("controller.closedRunning"));
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
    open.chat.onDispatched = (dispatched) => this.whereSent(dispatched);
    open.chat.onRouted = (threadId) => this.routedTo(open, threadId);
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
    return {
      chats: this.open.map((o) => ({ key: o.key, state: o.chat.getSnapshot() })),
      activeKey: this.activeKey,
      moving: this.mover?.getSnapshot().approval ?? null,
    };
  }
}

function newKey(): string {
  return crypto.randomUUID().slice(0, 8);
}

/** Two saved conversations can reopen as the same one; the first stays. */
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
