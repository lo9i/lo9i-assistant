// Daemon events for the whole page: one /events stream, handed to whoever registered for a kind
// (like clients/terminal/src/assistant_terminal/tui/live.py, but any part of the page can listen).
import type { DaemonClient } from "./client";
import { isAbort } from "./errors";
import type { BusEvent } from "./types";

export type Handler = (data: Record<string, unknown>) => unknown;

/** Whether the daemon can be reached: its event stream is opening for the first time, open, or lost and being
 * opened again (a daemon restarting, a computer that slept, a network that dropped). */
export type Connection = "connecting" | "open" | "lost";

export class EventHub {
  private readonly handlers = new Map<string, Set<Handler>>();
  private readonly reconnectHandlers = new Set<() => void>();
  private readonly connectionListeners = new Set<() => void>();
  private opened = false;
  private connection: Connection = "connecting";

  /** `report` hears a handler's error, which stops neither the other handlers nor the stream. */
  constructor(private readonly report: (error: unknown) => void = (error) => console.error("Event handler failed", error)) {}

  /** Calls `handler` for each event of these kinds; returns what stops it. */
  on(kinds: string[], handler: Handler): () => void {
    kinds.forEach((kind) => this.handlersOf(kind).add(handler));
    return () => kinds.forEach((kind) => this.handlers.get(kind)?.delete(handler));
  }

  /** Handlers run without waiting, so a slow one doesn't hold back the events after it. One that fails is
   * reported: the events after it still reach every handler, the stream stays open. */
  dispatch(event: BusEvent): void {
    this.handlers.get(event.kind)?.forEach((handler) => this.run(handler, event.data));
  }

  private run(handler: Handler, data: Record<string, unknown>): void {
    try {
      const result = handler(data);
      if (result instanceof Promise) result.catch(this.report);
    } catch (error) {
      this.report(error);
    }
  }

  /** Calls `handler` each time the stream opens again after a dropped connection, such as when the daemon is
   * back after a restart; returns what stops it. */
  onReconnect(handler: () => void): () => void {
    this.reconnectHandlers.add(handler);
    return () => this.reconnectHandlers.delete(handler);
  }

  /** Follows the connection's state, for showing whether the daemon can be reached. */
  subscribeConnection = (listener: () => void): (() => void) => {
    this.connectionListeners.add(listener);
    return () => this.connectionListeners.delete(listener);
  };

  getConnection = (): Connection => this.connection;

  /** Reads the daemon's events until `signal` aborts. */
  async listen(client: DaemonClient, signal: AbortSignal): Promise<void> {
    const opened = () => this.streamOpened();
    const lost = () => this.setConnection("lost");
    try {
      for await (const event of client.events(signal, opened, lost)) this.dispatch(event);
    } catch (error) {
      if (!isAbort(error)) throw error;
    }
  }

  private streamOpened(): void {
    this.setConnection("open");
    if (this.opened) this.reconnectHandlers.forEach((handler) => handler());
    this.opened = true;
  }

  private setConnection(connection: Connection): void {
    if (connection === this.connection) return;
    this.connection = connection;
    this.connectionListeners.forEach((listener) => listener());
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
