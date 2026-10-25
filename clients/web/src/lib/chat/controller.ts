// The conversation on the page, like the chat parts of src/assistant/gateways/cli/tui/app.py:
// sending, approvals, stopping, moving between conversations, and showing runs started elsewhere
// (another client, or a channel like Telegram). React reads it through subscribe/getSnapshot (useSyncExternalStore).
import { ApiError } from "../api/errors";
import { LiveConversation, type Conversations } from "../api/live";
import type { ApprovalRequired, Decision, Dispatched, RunAnnounced, RunEvent, RunFinished, Session, ShownConversation } from "../api/types";
import type { NoticeBoard } from "../notices";
import { ChatTab, type Place } from "./tab";
import { addCarried, addNotice, addUser, apply, empty, endRun, endText, fromHistory, type Transcript } from "./transcript";

/** The DaemonClient calls the chat needs. */
export interface ChatClient extends Conversations {
  send(session: Session, text: string, files: File[], signal: AbortSignal): AsyncIterable<RunEvent>;
  sendDispatched(session: Session, dispatchId: string, text: string, signal: AbortSignal): AsyncIterable<RunEvent>;
  moveDispatched(session: Session, dispatchId: string, signal: AbortSignal): AsyncIterable<RunEvent>;
  resume(session: Session, decisions: Record<string, Decision>, signal: AbortSignal): AsyncIterable<RunEvent>;
  cancel(session: Session): Promise<boolean>;
  followRunBatches(runId: string, signal: AbortSignal): AsyncIterable<RunEvent[]>;
  conversations: {
    live(threadId: string): Promise<ShownConversation>;
    approvals(threadId: string): Promise<ApprovalRequired[]>;
  };
}

type Start = (signal: AbortSignal) => AsyncIterable<RunEvent>;

/** A run to show from its start, as its `run` event announced it or the conversation lists it in progress. */
type Followed = Pick<RunAnnounced, "run_id" | "channel" | "client_id" | "text" | "notice">;

/** A message waiting for the reply before it to finish. One the inbox sent on here (`dispatched`) can't be taken
 * back: the daemon keeps it as sent on. `after` is called once its own reply has finished. */
export type Queued = { text: string; files: File[]; dispatched?: Dispatched; after?: (chat: ChatController) => unknown };

export type ChatSnapshot = {
  threadId: string;
  // The inbox's id: a message written there is routed to its conversation (core/inbox.py).
  inboxId: string;
  transcript: Transcript;
  // This page's own reply is running.
  busy: boolean;
  // A reply started from another channel is being shown.
  mirroring: boolean;
  approval: ApprovalRequired | null;
  // Messages to send here once nothing runs, oldest first.
  queued: Queued[];
};

const EXCERPT = 160;

export class ChatController {
  private state: ChatSnapshot;
  private readonly listeners = new Set<() => void>();
  // Aborting one stops showing that run's events; the run keeps going in the daemon.
  private ownRun: AbortController | null = null;
  // The inbox's run sent its message on, and the run where it went hasn't started yet: still busy, so the
  // input doesn't come back for a moment between the two.
  private handingOn = false;
  private readonly mirrors = new Set<AbortController>();
  // The runs shown in this transcript, by id: one in progress on opening that is also announced shows once.
  private followed = new Set<string>();
  // The conversation's history loading: a run announced meanwhile shows after it, unless it's among its runs.
  private loading: Promise<unknown> = Promise.resolve();
  private decide: ((decision: Decision) => void) | null = null;

  private constructor(
    private readonly client: ChatClient,
    private readonly live: LiveConversation,
    private readonly notices: NoticeBoard,
    transcript: Transcript,
    inboxId: string,
    private readonly tab: ChatTab,
    place: Place,
  ) {
    this.state = { threadId: live.session.thread_id, inboxId, transcript, busy: false, mirroring: false, approval: null, queued: [] };
    tab.join(this, place);
  }

  /** Opens on `earlier`, the conversation this tab was on before a reload, or the inbox, as one of `tab`'s chats. */
  static async open(
    client: ChatClient,
    channel: string,
    earlier: string | null,
    notices: NoticeBoard,
    tab = new ChatTab(),
    place: Place = "chat",
  ): Promise<ChatController> {
    const inboxId = await client.inboxThread();
    const threadId = await rejoin(client, earlier, inboxId);
    const live = new LiveConversation(client, { channel, thread_id: threadId });
    const chat = new ChatController(client, live, notices, empty, inboxId, tab, place);
    try {
      await chat.showHistory();
    } catch (error) {
      chat.close();
      throw error;
    }
    void chat.answerPending();
    return chat;
  }

  /** Opens on a new conversation, beside the ones open already. */
  static async openNew(client: ChatClient, channel: string, notices: NoticeBoard, tab = new ChatTab()): Promise<ChatController> {
    const inboxId = await client.inboxThread();
    const live = new LiveConversation(client, { channel, thread_id: await client.newThread() });
    return new ChatController(client, live, notices, empty, inboxId, tab, "chat");
  }

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  getSnapshot = (): ChatSnapshot => this.state;

  async send(text: string, files: File[]): Promise<void> {
    const names = files.map((f) => f.name);
    await this.own(text, names, (signal) => this.client.send(this.live.session, text, files, signal));
  }

  /** Writes in the inbox, from wherever this is: the inbox sends the message on to its conversation, and
   * this goes there with it (or stays in the inbox for a quick answer). */
  async write(text: string, files: File[]): Promise<void> {
    if (this.ownRun !== null) return;
    if (this.state.threadId !== this.state.inboxId) await this.goInbox();
    await this.send(text, files);
  }

  /** Sends here a message the inbox sent on, as it was written, after the quick exchange it followed up, and then
   * `following`, the messages queued in the inbox behind it; `started` is called once its run has. While a run goes
   * on here, it waits in the queue for it to finish, and `started` is called at once. */
  async sendDispatched(dispatched: Dispatched, started: () => void = () => {}, following: Queued[] = []): Promise<void> {
    const { id, text, carried } = dispatched;
    if (this.ownRun !== null || this.mirrors.size > 0) {
      this.set({ queued: [...this.state.queued, { text, files: [], dispatched }, ...following] });
      return started();
    }
    this.set({ queued: [...this.state.queued, ...following] });
    if (carried) this.set({ transcript: addCarried(this.state.transcript, carried) });
    await this.own(text, [], (signal) => this.client.sendDispatched(this.live.session, id, text, signal), started);
  }

  /** Sends `text` and `files` once nothing runs here, after the messages queued before it; at once when nothing does.
   * `after` is called once its reply has finished. */
  queue(text: string, files: File[], after?: (chat: ChatController) => unknown): void {
    this.set({ queued: [...this.state.queued, { text, files, after }] });
    this.sendQueued();
  }

  /** Takes back the queued message at `index` and returns it; not one the inbox sent on, which stays. */
  unqueue(index: number): Queued | null {
    const item = this.state.queued[index];
    if (!item || item.dispatched) return null;
    this.set({ queued: this.state.queued.filter((_, i) => i !== index) });
    return item;
  }

  /** Asks in the inbox where a message it sent on goes instead (the last one for ""), and sends it there. */
  async move(dispatchId: string): Promise<void> {
    await this.ownTurn((signal) => this.client.moveDispatched(this.live.session, dispatchId, signal));
  }

  /** The chat a message the inbox sent on goes to, which sends it there (null when it can't be shown); without one,
   * this conversation goes there. */
  onDispatched: ((dispatched: Dispatched) => Promise<ChatController | null>) | null = null;

  /** This page's own run of a message, from `start`. */
  private async own(text: string, files: string[], start: Start, started: () => void = () => {}): Promise<void> {
    if (this.ownRun !== null) return;
    this.set({ transcript: addUser(this.state.transcript, text, files) });
    await this.ownTurn(start, started);
  }

  /** This page's own run, from `start`; after it, the conversation goes where the inbox sent its message on. */
  private async ownTurn(start: Start, started: () => void = () => {}): Promise<void> {
    if (this.ownRun !== null) return;
    const run = new AbortController();
    this.ownRun = run;
    let dispatched: Dispatched | null = null;
    await this.show(run, async () => {
      started();
      dispatched = await this.turn(start, run.signal);
    });
    if (this.ownRun === run) this.ownRun = null;
    if (dispatched !== null) await this.handOn(dispatched);
    this.showing();
    this.sendQueued();
  }

  /** Goes on where the inbox sent its message, busy until the run there has started. The messages queued here
   * until then follow it there; once it has, what's written here is sent here. */
  private async handOn(dispatched: Dispatched): Promise<void> {
    this.handingOn = true;
    const started = () => {
      this.handingOn = false;
      this.showing();
      this.sendQueued();
    };
    try {
      const there = await (this.onDispatched ?? ((d) => this.goOn(d)))(dispatched);
      await there?.sendDispatched(dispatched, started, this.takeQueued());
    } finally {
      this.handingOn = false;
    }
  }

  /** The next queued message, once nothing runs here. */
  private sendQueued(): void {
    if (this.ownRun !== null || this.handingOn || this.mirrors.size > 0) return;
    const [next, ...rest] = this.state.queued;
    if (!next) return;
    this.set({ queued: rest });
    if (next.dispatched) void this.sendDispatched(next.dispatched);
    else void this.send(next.text, next.files).then(() => next.after?.(this));
  }

  private takeQueued(): Queued[] {
    const queued = this.state.queued;
    this.set({ queued: [] });
    return queued;
  }

  /** Stop the reply in progress, whichever channel started it. */
  async stop(): Promise<void> {
    await this.guarded(() => this.client.cancel(this.live.session));
  }

  answer(decision: Decision): void {
    this.decide?.(decision);
  }

  async goInbox(): Promise<void> {
    await this.guarded(async () => {
      const stillRunning = this.stopShowing();
      await this.live.goInbox(stillRunning);
      this.set({ inboxId: this.live.session.thread_id });
      await this.showHistory();
      void this.answerPending();
      if (stillRunning) this.notify("In the inbox. The previous reply keeps running.");
    });
  }

  async startNew(): Promise<void> {
    await this.guarded(async () => {
      const stillRunning = this.stopShowing();
      await this.live.startNew(stillRunning);
      this.set({ threadId: this.live.session.thread_id, transcript: empty });
      this.notify(
        stillRunning
          ? "Started a new conversation. The previous reply keeps running; you'll be notified when it's done."
          : "Started a new conversation.",
      );
    });
  }

  async resume(threadId: string): Promise<void> {
    if (threadId === this.live.session.thread_id) return;
    await this.guarded(async () => {
      const stillRunning = this.ownRun !== null;
      await this.live.resume(threadId, stillRunning);
      this.stopShowing();
      await this.showHistory();
      void this.answerPending();
      this.notify("Resumed the conversation." + (stillRunning ? " The previous reply keeps running." : ""));
    });
  }

  /** Show a run started elsewhere in this conversation as it happens. */
  async mirror(run: RunAnnounced): Promise<void> {
    await this.loaded();
    if (!this.live.startedElsewhere(run) || this.followed.has(run.run_id)) return;
    // Another client answered what this page is asking, and goes on with the run there.
    if (this.decide !== null) this.ownRun?.abort();
    await this.follow([run]);
  }

  runFinished(run: RunFinished): void {
    // A run started anywhere, this page watching it or not, may have stopped to ask the user.
    if (run.thread_id === this.live.session.thread_id) void this.answerPending();
    if (!this.live.leftRunFinished(run)) return;
    const excerpt = run.reply.length > EXCERPT ? run.reply.slice(0, EXCERPT) + "…" : run.reply;
    this.notify(`Previous conversation finished: ${excerpt || run.status}`, run.status === "ok" ? "info" : "warning");
  }

  /** Stop showing every run, for good; the daemon keeps them going. */
  close(): void {
    this.stopShowing();
    this.tab.leave(this);
  }

  /** Closes the conversation for good: the daemon leaves it unless another client is on it. Returns whether
   * its reply was still running, which the daemon finishes. */
  async leave(): Promise<boolean> {
    const stillRunning = this.stopShowing();
    this.tab.leave(this);
    await this.guarded(() => this.client.leaveThread());
    return stillRunning;
  }

  /** Runs the turn and returns where the inbox sent its message on, if it did. */
  private async turn(start: Start, signal: AbortSignal): Promise<Dispatched | null> {
    let shown = await this.render(singly(start(signal)));
    let dispatched = shown.dispatched;
    while (shown.approvals.length) {
      shown = await this.render(singly(this.answered(shown.approvals, signal)));
      dispatched ??= shown.dispatched;
    }
    return dispatched;
  }

  /** Asks what the conversation's run stopped for and still waits on, whoever started it (another client, a
   * channel, the daemon's queued runs, or this page before a reload), and goes on with the answers as this
   * page's own run. */
  private async answerPending(): Promise<void> {
    if (this.ownRun !== null) return;
    const threadId = this.live.session.thread_id;
    let waiting: ApprovalRequired[] = [];
    await this.guarded(async () => (waiting = await this.client.conversations.approvals(threadId)));
    if (!waiting.length || threadId !== this.live.session.thread_id || !this.tab.asks(this, threadId)) return;
    await this.ownTurn((signal) => this.answered(waiting, signal));
  }

  /** The run going on with the user's answers to `approvals`, once they gave them. */
  private async *answered(approvals: ApprovalRequired[], signal: AbortSignal): AsyncIterable<RunEvent> {
    const decisions: Record<string, Decision> = {};
    for (const approval of approvals) decisions[approval.interrupt_id] = await this.ask(approval, signal);
    yield* this.client.resume(this.live.session, decisions, signal);
  }

  /** The inbox sent the message on: this conversation goes to where it went, or a new one, to send it there; null
   * when it can't. */
  private async goOn(dispatched: Dispatched): Promise<ChatController | null> {
    try {
      if (dispatched.thread_id) {
        await this.live.resume(dispatched.thread_id);
        await this.showHistory();
      } else {
        await this.live.startNew();
        this.set({ threadId: this.live.session.thread_id, transcript: empty });
      }
      return this;
    } catch (error) {
      this.report(error);
      return null;
    }
  }

  /** Shows runs not shown yet from their start, one after another as they run, until the page stops showing them. */
  private async follow(runs: Followed[]): Promise<void> {
    const unseen = runs.filter((run) => !this.followed.has(run.run_id));
    if (!unseen.length) return;
    unseen.forEach((run) => this.followed.add(run.run_id));
    const following = new AbortController();
    this.mirrors.add(following);
    for (const run of unseen) {
      if (following.signal.aborted) break;
      this.showStarted(run);
      await this.show(following, () => this.render(this.client.followRunBatches(run.run_id, following.signal)));
    }
    this.mirrors.delete(following);
    this.showing();
    this.sendQueued();
  }

  /** What a run answers, where the user's message would be: what they wrote, from where when it wasn't this page,
   * or the notice of a follow-up. */
  private showStarted(run: Followed): void {
    const channel = run.client_id === this.client.clientId ? undefined : run.channel;
    if (run.text) this.set({ transcript: addUser(this.state.transcript, run.text, [], channel) });
    if (run.notice) this.set({ transcript: addNotice(this.state.transcript, run.notice) });
  }

  /** Show the events and return the approvals the run is waiting on, and where the inbox sent its message on. Each
   * batch is one update of the page, however many events it has. */
  private async render(batches: AsyncIterable<RunEvent[]>): Promise<{ approvals: ApprovalRequired[]; dispatched: Dispatched | null }> {
    const approvals: ApprovalRequired[] = [];
    let dispatched: Dispatched | null = null;
    try {
      for await (const batch of batches) {
        let transcript = this.state.transcript;
        for (const event of batch) {
          if (event.type === "ApprovalRequired") approvals.push(event);
          else if (event.type === "Dispatched") dispatched = event;
          if (event.type !== "ApprovalRequired") transcript = apply(transcript, event);
        }
        this.set({ transcript });
      }
    } finally {
      this.set({ transcript: endText(this.state.transcript) });
    }
    return { approvals, dispatched };
  }

  private ask(approval: ApprovalRequired, signal: AbortSignal): Promise<Decision> {
    this.set({ approval });
    return new Promise<Decision>((resolve, reject) => {
      const settle = () => {
        signal.removeEventListener("abort", aborted);
        this.decide = null;
        this.set({ approval: null });
      };
      const aborted = () => {
        settle();
        reject(signal.reason);
      };
      this.decide = (decision) => {
        settle();
        resolve(decision);
      };
      signal.addEventListener("abort", aborted, { once: true });
    });
  }

  private async show(run: AbortController, work: () => Promise<unknown>): Promise<void> {
    this.showing();
    try {
      await work();
    } catch (error) {
      if (!run.signal.aborted) this.report(error);
    } finally {
      this.set({ transcript: endRun(this.state.transcript) });
    }
  }

  private showing(): void {
    this.set({ busy: this.ownRun !== null || this.handingOn, mirroring: this.mirrors.size > 0 });
  }

  /** Stops showing runs, and drops the messages queued for this conversation, which the page leaves; returns whether
   * this page's own reply was running. */
  private stopShowing(): boolean {
    const wasBusy = this.ownRun !== null;
    this.ownRun?.abort();
    this.ownRun = null;
    this.stopFollowing();
    this.set({ transcript: endRun(this.state.transcript), queued: [] });
    this.showing();
    return wasBusy;
  }

  /** Stops showing runs started elsewhere; the daemon keeps them going. */
  private stopFollowing(): void {
    this.mirrors.forEach((mirror) => mirror.abort());
    this.mirrors.clear();
    this.followed = new Set();
  }

  /** Shows the conversation's history up to its runs in progress, then those runs from their start, as if the page
   * had been watching them. */
  private async showHistory(): Promise<void> {
    const threadId = this.live.session.thread_id;
    const loading = this.client.conversations.live(threadId);
    this.loading = loading.catch(() => {});
    const { messages, runs } = await loading;
    this.stopFollowing();
    this.set({ threadId, transcript: fromHistory(messages) });
    this.showing();
    void this.follow(runs);
  }

  /** Returns once the conversation's history has loaded, the latest load if another started meanwhile. */
  private async loaded(): Promise<void> {
    let loading: Promise<unknown>;
    do {
      loading = this.loading;
      await loading;
    } while (loading !== this.loading);
  }

  private async guarded(action: () => Promise<unknown>): Promise<void> {
    try {
      await action();
    } catch (error) {
      this.report(error);
    }
  }

  private report(error: unknown): void {
    this.notices.report(error);
  }

  private notify(text: string, level: "info" | "warning" = "info"): void {
    this.notices.notify(text, level);
  }

  private set(change: Partial<ChatSnapshot>): void {
    this.state = { ...this.state, ...change };
    this.listeners.forEach((listener) => listener());
  }
}

/** Each event as a batch of its own: a run this page started streams as it's written. */
async function* singly(events: AsyncIterable<RunEvent>): AsyncGenerator<RunEvent[]> {
  for await (const event of events) yield [event];
}

/** The conversation to open on: `earlier` if the daemon still has it, else the inbox. A conversation
 * without messages isn't saved, so the daemon doesn't know it. */
async function rejoin(client: ChatClient, earlier: string | null, inboxId: string): Promise<string> {
  if (earlier === null) return inboxId;
  try {
    await client.resumeThread(earlier);
    return earlier;
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return inboxId;
    throw error;
  }
}
