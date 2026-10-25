// The daemon's health checks (core/doctor/), as the Health page and the alerts show them.
import type { Alert, Cause, ContextPart, StartingContext } from "./api/types";
import { compact } from "./conversationStats";

/** "New", "Growing" or "", against the day before. */
export function changeLabel(cause: Cause): string {
  return cause.change === "new" ? "New" : cause.change === "growing" ? "Growing" : "";
}

/** Like "3 times" or "3 times (1 the day before)". */
export function times(cause: Cause): string {
  const count = cause.count === 1 ? "Once" : `${cause.count} times`;
  return cause.change === "growing" ? `${count} (${cause.before} the day before)` : count;
}

/** The share of the window the starting context takes, like "18%". */
export function contextShare(context: StartingContext): string {
  return context.window ? `${Math.round((100 * context.tokens) / context.window)}%` : "?";
}

/** A part's size and how it changed since the day before, like "3.1k (+800)". */
export function partSize(part: ContextPart): string {
  const size = compact(part.tokens);
  if (part.before === null || part.before === undefined || part.before === part.tokens) return size;
  const change = part.tokens - part.before;
  return `${size} (${change > 0 ? "+" : "−"}${compact(Math.abs(change))})`;
}

/** What a health check's alert is about, for the Alerts page. */
export function doctorProblem(alert: Alert): string {
  if (alert.kind === "context") return "Starting context large";
  const count = alert.failures === 1 ? "once" : `${alert.failures} times`;
  return `${alert.kind === "new" ? "New" : "Growing"}, ${count}`;
}
