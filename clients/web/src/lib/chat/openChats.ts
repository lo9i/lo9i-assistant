// The conversations this browser tab has open side by side, each a ChatController under a client id of
// its own, so the daemon keeps every one of them open and their replies run in parallel. One is shown at a
// time; the sidebar lists them all. There can be none: Chat then shows the list of conversations. None of them is ever the inbox: it routes each message to its conversation
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
  // The one shown; null with none open.
  activeKey: string | null;
  // What the inbox asks while /move runs there (which conversation the message goes to instead).
  moving: ApprovalRequired | null;
};

export class OpenChats {
  private readonly listeners = new Set<() => void>();
  private snapshot: OpenChatsSnapshot;
  private readonly unsubscribe = new Map<string, () => void>();
  // The chat on the inbox a move runs in, kept out of the open ones for as long as it runs.
  private mover: ChatController | null = null;
  // The conversations being opened beside the others, so one asked for twice at once opens once.
  private readonly opening = new Map<string, Promise<ChatController | null>>();

  private constructor(
    private readonly clientFor: ClientFor,
    private readonly channel: string,
    private readonly notices: NoticeBoard,
    private readonly tab: ChatTab,
    private open: OpenChat[],
    private activeKey: string | null,
    /** The inbox's id, which no open conversation is on. */
    readonly inboxId: string,
  ) {
    this.snapshot = this.build();
    open.forEach((o) => this.follow(o));
  }

  /** Reopens `threads`, the conversations open before a reload (the first under the tab's own client id),
   * showing the one at `active`; a new one for null, as for one that's gone or was the inbox. With none, opens none.
   * Each is one of `tab`'s chats. */
  static async open(
    clientFor: ClientFor,
    channel: string,
    threads: (string | null)[],
    active: number,
    notices: NoticeBoard,
    tab = new ChatTab(),
  ): Promise<OpenChats> {
    const opened = await Promise.all(
      threads.map(async (threadId, i) => {
        const key = i === 0 ? "" : newKey();
        return { key, chat: await ChatController.openInChat(clientFor(key || null), channel, threadId, notices, tab) };
      }),
    );
    const open = withoutRepeats(opened);
    const shown = opened[active] && open.includes(opened[active]) ? opened[active] : open[0];
    // Each chat learned the inbox's id on opening; with none, the tab's own client asks, which no chat is on.
    const inboxId = open[0]?.chat.getSnapshot().inboxId ?? (await clientFor(null).inboxThread());
    return new OpenChats(clientFor, channel, notices, tab, open, shown?.key ?? null, inboxId);
  }

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  getSnapshot = (): OpenChatsSnapshot => this.snapshot;

  /** The conversation shown; null with none open. */
  get current(): ChatController | null {
    return (this.open.find((o) => o.key === this.activeKey) ?? this.open[0])?.chat ?? null;
  }

  all(): ChatController[] {
    return this.open.map((o) => o.chat);
  }

  /** The conversations open, as their ids, and which one is shown (-1 with none); what a reload reopens. */
  saved(): { threads: string[]; active: number } {
    const threads = this.open.map((o) => o.chat.getSnapshot().threadId);
    return { threads, active: this.open.findIndex((o) => o.key === this.activeKey) };
  }

  activate(key: string): void {
    if (key === this.activeKey || !this.open.some((o) => o.key === key)) return;
    this.activeKey = key;
    this.changed();
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

  /** The open conversation on `threadId`, if any. */
  find(threadId: string): ChatController | null {
    return this.open.find((o) => o.chat.getSnapshot().threadId === threadId)?.chat ?? null;
  }

  /** The open conversation on `threadId`, opened beside the others without showing it when it isn't (a card replied
   * from, a conversation side by side); null for the inbox or one that's gone. Asked twice at once, it opens once. */
  async opened(threadId: string): Promise<ChatController | null> {
    if (threadId === this.inboxId) return null;
    const open = this.find(threadId);
    if (open) return open;
    const opening = this.opening.get(threadId) ?? this.openBeside(threadId);
    this.opening.set(threadId, opening);
    try {
      return await opening;
    } finally {
      this.opening.delete(threadId);
    }
  }

  private async openBeside(threadId: string): Promise<ChatController | null> {
    try {
      return await this.add(
        (client) => ChatController.openExisting(client, this.channel, threadId, this.inboxId, this.notices, this.tab),
        false,
      );
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) return null;
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

  /** Closes an open conversation, showing the next one, or none after the last. A reply still running keeps going
   * in the daemon. */
  async close(key: string): Promise<void> {
    const index = this.open.findIndex((o) => o.key === key);
    if (index < 0) return;
    const [closed] = this.open.splice(index, 1);
    this.unsubscribe.get(key)?.();
    this.unsubscribe.delete(key);
    if (this.activeKey === key) this.activeKey = this.open[Math.min(index, this.open.length - 1)]?.key ?? null;
    this.changed();
    if (await closed.chat.leave()) this.notices.notify(t("controller.closedRunning"));
  }

  /** Closes the open conversation `chat` shows, as close does (/close in it). */
  async closeChat(chat: ChatController): Promise<void> {
    const key = this.open.find((o) => o.chat === chat)?.key;
    if (key !== undefined) await this.close(key);
  }

  /** Stop showing every run; the daemon keeps them going. */
  closeAll(): void {
    this.open.forEach((o) => o.chat.close());
  }

  /** Opens a chat beside the others, shown unless `show` is false (and another one is). */
  private async add(opening: (client: ChatClient) => Promise<ChatController>, show = true): Promise<ChatController> {
    const key = newKey();
    const chat = await opening(this.clientFor(key));
    const opened = { key, chat };
    this.open.push(opened);
    this.follow(opened);
    if (show || this.activeKey === null) this.activeKey = key;
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
