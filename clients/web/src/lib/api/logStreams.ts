// The logs a tab follows, over its one /events stream (src/assistant/daemon/follows.py), as its runs are
// (runStreams.ts): a stream of its own per log took one more of the six HTTP/1.1 connections a browser keeps open to a
// plain-HTTP origin. Each log followed is asked for under an id of its own; its page and then each new entry come down
// the event stream, and each time that stream opens again every log is asked for again and starts with a new page.
import type { Transport } from "./transport";
import type { LogEntry, LogEvent, LogPage, LogQuery } from "./types";

// The event stream's kinds for a followed log (LOG_PAGE and LOG_ENTRY in follows.py).
const LOG_PAGE = "log_page";
const LOG_ENTRY = "log_entry";

class Follower {
  events: LogEvent[] = [];
  failed: { error: unknown } | null = null;
  private wake: (() => void) | null = null;

  constructor(
    readonly name: string,
    readonly query: LogQuery,
  ) {}

  add(event: LogEvent): void {
    this.events.push(event);
    this.woken();
  }

  fail(error: unknown): void {
    this.failed = { error };
    this.woken();
  }

  /** Waits for news: an event, a failure, or `signal` aborting. */
  news(signal: AbortSignal): Promise<void> {
    signal.throwIfAborted();
    if (this.events.length || this.failed) return Promise.resolve();
    return new Promise((resolve, reject) => {
      const aborted = () => reject(signal.reason);
      signal.addEventListener("abort", aborted, { once: true });
      this.wake = () => {
        signal.removeEventListener("abort", aborted);
        resolve();
      };
    });
  }

  private woken(): void {
    const wake = this.wake;
    this.wake = null;
    wake?.();
  }
}

export class LogStreams {
  private readonly followers = new Map<string, Follower>();

  /** `transport` is the one the event stream is read with: the daemon sends a log down the stream of the client
   * that asked for it. */
  constructor(private readonly transport: Transport) {}

  /** The log's page, then each new matching entry, until `signal` aborts; after the stream opens again, a new page.
   * Throws ApiError (400) for an unknown component, 404 for an unknown log. */
  async *follow(name: string, query: LogQuery, signal: AbortSignal): AsyncGenerator<LogEvent> {
    const id = crypto.randomUUID();
    const follower = new Follower(name, query);
    this.followers.set(id, follower);
    try {
      await this.ask(id, follower);
      for (;;) {
        await follower.news(signal);
        if (follower.failed) throw follower.failed.error;
        yield* follower.events.splice(0);
      }
    } finally {
      this.followers.delete(id);
      this.forget(id);
    }
  }

  /** Takes a followed log's event from the stream; false for any other. */
  receive(kind: string, data: Record<string, unknown>): boolean {
    if (kind !== LOG_PAGE && kind !== LOG_ENTRY) return false;
    const follower = this.followers.get(data.follow as string);
    if (kind === LOG_PAGE) follower?.add({ kind: "page", page: data.page as LogPage });
    else follower?.add({ kind: "entry", entry: data.entry as LogEntry });
    return true;
  }

  /** The stream opened again: every log is asked for again, and starts with a new page. */
  reopened(): void {
    this.followers.forEach((follower, id) => void this.ask(id, follower).catch((e: unknown) => follower.fail(e)));
  }

  private async ask(id: string, follower: Follower): Promise<void> {
    const { level, component, lines } = follower.query;
    const body = { name: follower.name, lines, component, ...(level ? { level } : {}) };
    await this.transport.request("PUT", `/events/logs/${encodeURIComponent(id)}`, body);
  }

  /** Not waited for: what the daemon can't hear now it forgets once this tab's stream stays closed. */
  private forget(id: string): void {
    this.transport.request("DELETE", `/events/logs/${encodeURIComponent(id)}`).catch(() => {});
  }
}
