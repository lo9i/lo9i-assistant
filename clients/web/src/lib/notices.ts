// Short messages shown in the corner: what just happened, and errors from any page.
import { ApiError, DaemonUnavailableError } from "./api/errors";

/** What a notice offers to do about it, such as opening the conversation it's about. */
export type NoticeAction = { label: string; run: () => void };

export type Notice = { id: number; text: string; level: "info" | "warning" | "error"; action?: NoticeAction };

export class NoticeBoard {
  private notices: Notice[] = [];
  private readonly listeners = new Set<() => void>();
  private nextId = 1;

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  getSnapshot = (): Notice[] => this.notices;

  notify = (text: string, level: Notice["level"] = "info", action?: NoticeAction): void => {
    this.set([...this.notices, { id: this.nextId++, text, level, action }]);
  };

  /** Shows an error from a daemon call. */
  report = (error: unknown): void => {
    this.notify(describe(error), "error");
  };

  dismiss = (id: number): void => {
    this.set(this.notices.filter((n) => n.id !== id));
  };

  private set(notices: Notice[]): void {
    this.notices = notices;
    this.listeners.forEach((listener) => listener());
  }
}

/** What went wrong with a daemon call, for showing it. */
export function describe(error: unknown): string {
  if (error instanceof DaemonUnavailableError) return "Can't reach the daemon. Is it running?";
  if (error instanceof ApiError) return error.detail;
  return String(error);
}
