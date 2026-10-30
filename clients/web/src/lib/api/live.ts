// The conversation the page shows, like src/assistant/client/live.py: which conversation this
// client is on, which runs in it come from elsewhere (another client, or a channel like Telegram),
// and which replies were left running after moving to another conversation.
import type { RunAnnounced, RunFinished, SentOn, Session } from "./types";

/** The DaemonClient calls LiveConversation needs. */
export interface Conversations {
  readonly clientId: string;
  inboxThread(): Promise<string>;
  newThread(): Promise<string>;
  resumeThread(threadId: string): Promise<void>;
  leaveThread(): Promise<void>;
}

export class LiveConversation {
  // Conversations left with a reply still running; the daemon finishes those replies.
  private readonly leftRunning = new Set<string>();

  constructor(
    private readonly client: Conversations,
    public session: Session,
  ) {}

  /** Move to a new conversation. With `leaveRunning`, the reply running in the current one keeps
   * going in the daemon, and `leftRunFinished` reports when it ends. */
  async startNew(leaveRunning = false): Promise<void> {
    if (leaveRunning) this.leftRunning.add(this.session.thread_id);
    this.session = { ...this.session, thread_id: await this.client.newThread() };
  }

  /** Move to the inbox, like `startNew`. */
  async goInbox(leaveRunning = false): Promise<void> {
    if (leaveRunning) this.leftRunning.add(this.session.thread_id);
    this.session = { ...this.session, thread_id: await this.client.inboxThread() };
  }

  /** Move back to an earlier conversation, like `startNew`. Throws ApiError for an unknown one. */
  async resume(threadId: string, leaveRunning = false): Promise<void> {
    await this.client.resumeThread(threadId);
    if (leaveRunning) this.leftRunning.add(this.session.thread_id);
    this.session = { ...this.session, thread_id: threadId };
  }

  /** A run in this conversation, started by anything but this client. */
  startedElsewhere(run: RunAnnounced): boolean {
    return run.thread_id === this.session.thread_id && run.client_id !== this.client.clientId;
  }

  /** A message this client wrote in this conversation (the inbox) while an update installed, which the daemon sent
   * on after it: the client goes where it went, as after a Dispatched of its own run. */
  sentHere(sent: SentOn): boolean {
    return sent.client_id === this.client.clientId && sent.from_thread_id === this.session.thread_id;
  }

  /** True, once, when a finished run is one left with `startNew` or `resume`. */
  leftRunFinished(run: RunFinished): boolean {
    return this.leftRunning.delete(run.thread_id);
  }
}
