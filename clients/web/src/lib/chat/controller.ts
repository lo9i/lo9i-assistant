// The conversation on the page, like the chat parts of src/assistant/gateways/cli/tui/app.py:
// sending, approvals, stopping, moving between conversations, and showing runs started elsewhere
// (another client, or a channel like Telegram). React reads it through subscribe/getSnapshot (useSyncExternalStore).
import { ApiError } from "../api/errors";
import { LiveConversation, type Conversations } from "../api/live";
import type { ApprovalRequired, Decision, RunAnnounced, RunEvent, RunFinished, Session, ShownMessage } from "../api/types";
import type { NoticeBoard } from "../notices";
import { addUser, apply, empty, endRun, endText, fromHistory, type Transcript } from "./transcript";

/** The DaemonClient calls the chat needs. */
export interface ChatClient extends Conversations {
  send(session: Session, text: string, files: File[], signal: AbortSignal): AsyncIterable<RunEvent>;
  resume(session: Session, decisions: Record<string, Decision>, signal: AbortSignal): AsyncIterable<RunEvent>;
  cancel(session: Session): Promise<boolean>;
  followRun(runId: string, signal: AbortSignal): AsyncIterable<RunEvent>;
  conversations: { messages(threadId: string): Promise<ShownMessage[]> };
}

export type ChatSnapshot = {
  threadId: string;
  transcript: Transcript;
  // This page's own reply is running.
  busy: boolean;
  // A reply started from another channel is being shown.
  mirroring: boolean;
  approval: ApprovalRequired | null;
};

const EXCERPT = 160;

export class ChatController {
  private state: ChatSnapshot;
  private readonly listeners = new Set<() => void>();
  // Aborting one stops showing that run's events; the run keeps going in the daemon.
  private ownRun: AbortController | null = null;
  private readonly mirrors = new Set<AbortController>();
  private decide: ((decision: Decision) => void) | null = null;

  private constructor(
    private readonly client: ChatClient,
    private readonly live: LiveConversation,
    private readonly notices: NoticeBoard,
    transcript: Transcript,
  ) {
    this.state = { threadId: live.session.thread_id, transcript, busy: false, mirroring: false, approval: null };
  }

  /** Opens on `earlier`, the conversation this tab was on before a reload, or a new one. */
  static async open(client: ChatClient, channel: string, earlier: string | null, notices: NoticeBoard): Promise<ChatController> {
    const threadId = await rejoin(client, earlier);
    const history = threadId === earlier ? await client.conversations.messages(threadId) : [];
    const live = new LiveConversation(client, { channel, thread_id: threadId });
    return new ChatController(client, live, notices, fromHistory(history));
  }

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  getSnapshot = (): ChatSnapshot => this.state;

  async send(text: string, files: File[]): Promise<void> {
    if (this.ownRun !== null) return;
    this.set({
      transcript: addUser(
        this.state.transcript,
        text,
        files.map((f) => f.name),
      ),
    });
    const run = new AbortController();
    this.ownRun = run;
    await this.show(run, () => this.turn(text, files, run.signal));
    if (this.ownRun === run) this.ownRun = null;
    this.showing();
  }

  /** Stop the reply in progress, whichever channel started it. */
  async stop(): Promise<void> {
    await this.guarded(() => this.client.cancel(this.live.session));
  }

  answer(decision: Decision): void {
    this.decide?.(decision);
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
      this.notify("Resumed the conversation." + (stillRunning ? " The previous reply keeps running." : ""));
    });
  }

  /** Show a run started elsewhere in this conversation as it happens. */
  async mirror(run: RunAnnounced): Promise<void> {
    if (!this.live.startedElsewhere(run)) return;
    if (run.text) this.set({ transcript: addUser(this.state.transcript, run.text, [], run.channel) });
    const mirror = new AbortController();
    this.mirrors.add(mirror);
    await this.show(mirror, () => this.render(this.client.followRun(run.run_id, mirror.signal)));
    this.mirrors.delete(mirror);
    this.showing();
  }

  runFinished(run: RunFinished): void {
    if (!this.live.leftRunFinished(run)) return;
    const excerpt = run.reply.length > EXCERPT ? run.reply.slice(0, EXCERPT) + "…" : run.reply;
    this.notify(`Previous conversation finished: ${excerpt || run.status}`, run.status === "ok" ? "info" : "warning");
  }

  /** Stop showing every run; the daemon keeps them going. */
  close(): void {
    this.stopShowing();
  }

  private async turn(text: string, files: File[], signal: AbortSignal): Promise<void> {
    let approvals = await this.render(this.client.send(this.live.session, text, files, signal));
    while (approvals.length) {
      const decisions: Record<string, Decision> = {};
      for (const approval of approvals) decisions[approval.interrupt_id] = await this.ask(approval, signal);
      approvals = await this.render(this.client.resume(this.live.session, decisions, signal));
    }
  }

  /** Show the events and return the approvals the run is waiting on. */
  private async render(events: AsyncIterable<RunEvent>): Promise<ApprovalRequired[]> {
    const approvals: ApprovalRequired[] = [];
    try {
      for await (const event of events) {
        if (event.type === "ApprovalRequired") approvals.push(event);
        else this.set({ transcript: apply(this.state.transcript, event) });
      }
    } finally {
      this.set({ transcript: endText(this.state.transcript) });
    }
    return approvals;
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
    this.set({ busy: this.ownRun !== null, mirroring: this.mirrors.size > 0 });
  }

  /** Stops showing runs and returns whether this page's own reply was running. */
  private stopShowing(): boolean {
    const wasBusy = this.ownRun !== null;
    this.ownRun?.abort();
    this.ownRun = null;
    this.mirrors.forEach((mirror) => mirror.abort());
    this.mirrors.clear();
    this.set({ transcript: endRun(this.state.transcript) });
    this.showing();
    return wasBusy;
  }

  private async showHistory(): Promise<void> {
    const threadId = this.live.session.thread_id;
    this.set({ threadId, transcript: fromHistory(await this.client.conversations.messages(threadId)) });
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

/** The conversation to open on: `earlier` if the daemon still has it, else a new one. A conversation
 * without messages isn't saved, so the daemon doesn't know it. */
async function rejoin(client: ChatClient, earlier: string | null): Promise<string> {
  if (earlier === null) return client.newThread();
  try {
    await client.resumeThread(earlier);
    return earlier;
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return client.newThread();
    throw error;
  }
}
