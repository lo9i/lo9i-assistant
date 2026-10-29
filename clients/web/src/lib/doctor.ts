// The daemon's health checks (core/doctor/), as the Health page and the alerts show them.
import type { Alert, Cause, ContextPart, StartingContext } from "./api/types";
import { compact } from "./conversationStats";
import { t } from "./i18n.svelte";

/** "New", "Growing" or "", against the day before. */
export function changeLabel(cause: Cause): string {
  return cause.change === "new" ? t("doctor.new") : cause.change === "growing" ? t("doctor.growing") : "";
}

/** Like "3 times" or "3 times (1 the day before)". */
export function times(cause: Cause): string {
  const count = t("doctor.times", { count: cause.count });
  return cause.change === "growing" ? t("doctor.timesBefore", { count, before: cause.before }) : count;
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
  if (alert.kind === "context") return t("doctor.contextLarge");
  const count = t("doctor.timesLower", { count: alert.failures });
  return `${alert.kind === "new" ? t("doctor.new") : t("doctor.growing")}, ${count}`;
}
