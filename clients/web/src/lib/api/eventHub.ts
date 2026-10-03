// Daemon events for the whole page: one /events stream, handed to whoever registered for a kind
// (like src/assistant/gateways/cli/tui/live.py, but any part of the page can listen).
import type { DaemonClient } from "./client";
import { isAbort } from "./errors";
import type { BusEvent } from "./types";

export type Handler = (data: Record<string, unknown>) => unknown;

export class EventHub {
  private readonly handlers = new Map<string, Set<Handler>>();

  /** Calls `handler` for each event of these kinds; returns what stops it. */
  on(kinds: string[], handler: Handler): () => void {
    kinds.forEach((kind) => this.handlersOf(kind).add(handler));
    return () => kinds.forEach((kind) => this.handlers.get(kind)?.delete(handler));
  }

  /** Handlers run without waiting, so a slow one doesn't hold back the events after it. */
  dispatch(event: BusEvent): void {
    this.handlers.get(event.kind)?.forEach((handler) => void handler(event.data));
  }

  /** Reads the daemon's events until `signal` aborts. */
  async listen(client: DaemonClient, signal: AbortSignal): Promise<void> {
    try {
      for await (const event of client.events(signal)) this.dispatch(event);
    } catch (error) {
      if (!isAbort(error)) throw error;
    }
  }

  private handlersOf(kind: string): Set<Handler> {
    let set = this.handlers.get(kind);
    if (set === undefined) {
      set = new Set();
      this.handlers.set(kind, set);
    }
    return set;
  }
}
