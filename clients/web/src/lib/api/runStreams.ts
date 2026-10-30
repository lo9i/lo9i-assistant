// The runs a tab follows, over its one /events stream (src/assistant/daemon/run_follows.py). A browser keeps at most
// six HTTP/1.1 connections open to a plain-HTTP origin across all its tabs, and a stream per run used them up, so
// every other request of the page waited. Each run followed is asked for under an id of its own; its events come down
// the event stream with how many came before them, and each time that stream opens again every run is asked for
// again from where it got to, which drops what came twice.
import type { Transport } from "./transport";
import type { RunEvent } from "./types";

// The event stream's kinds for a followed run (RUN_EVENTS and RUN_END in run_follows.py).
const RUN_EVENTS = "run_events";
const RUN_END = "run_end";

class Follower {
  received = 0;
  batches: RunEvent[][] = [];
  ended = false;
  failed: { error: unknown } | null = null;
  private wake: (() => void) | null = null;

  constructor(readonly runId: string) {}

  /** Keeps the events not received yet; `after` is how many of the run's came before them. */
  add(after: number, events: RunEvent[]): void {
    const fresh = events.slice(Math.max(0, this.received - after));
    if (!fresh.length) return;
    this.received = after + events.length;
    this.batches.push(fresh);
    this.woken();
  }

  end(): void {
    this.ended = true;
    this.woken();
  }

  fail(error: unknown): void {
    this.failed = { error };
    this.woken();
  }

  /** Waits for news: events, the end, a failure, or `signal` aborting. */
  news(signal: AbortSignal): Promise<void> {
    signal.throwIfAborted();
    if (this.batches.length || this.ended || this.failed) return Promise.resolve();
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

export class RunStreams {
  private readonly followers = new Map<string, Follower>();

  /** `transport` is the one the event stream is read with: the daemon sends a run down the stream of the client
   * that asked for it. */
  constructor(private readonly transport: Transport) {}

  /** The run's events from its first, in the batches they came in, until its last. Throws ApiError (404) for a run
   * the daemon doesn't know, as after it restarted. */
  async *follow(runId: string, signal: AbortSignal): AsyncGenerator<RunEvent[]> {
    const id = crypto.randomUUID();
    const follower = new Follower(runId);
    this.followers.set(id, follower);
    try {
      await this.ask(id, follower);
      for (;;) {
        await follower.news(signal);
        if (follower.failed) throw follower.failed.error;
        yield* follower.batches.splice(0);
        if (follower.ended) return;
      }
    } finally {
      this.followers.delete(id);
      if (!follower.ended) this.forget(id);
    }
  }

  /** Takes a followed run's event from the stream; false for any other. */
  receive(kind: string, data: Record<string, unknown>): boolean {
    if (kind !== RUN_EVENTS && kind !== RUN_END) return false;
    const follower = this.followers.get(data.follow as string);
    if (kind === RUN_EVENTS) follower?.add(data.after as number, data.events as RunEvent[]);
    else follower?.end();
    return true;
  }

  /** The stream opened again: every run is asked for again from where it got to. */
  reopened(): void {
    this.followers.forEach((follower, id) => void this.ask(id, follower).catch((e: unknown) => follower.fail(e)));
  }

  private async ask(id: string, follower: Follower): Promise<void> {
    const body = { run_id: follower.runId, after: follower.received };
    await this.transport.request("PUT", `/events/runs/${encodeURIComponent(id)}`, body);
  }

  /** Not waited for: what the daemon can't hear now it forgets once this tab's stream stays closed. */
  private forget(id: string): void {
    this.transport.request("DELETE", `/events/runs/${encodeURIComponent(id)}`).catch(() => {});
  }
}
