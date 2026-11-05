// The daemon's health checks (core/doctor/), as the Health page and the alerts show them, and the setup check
// (core/setup_check/), the page's Setup card.
import type { Alert, Cause, ContextPart, SetupCheck, StartingContext } from "./api/types";
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

/** The setup check at a glance: how many fail, else how many warn, else all ok, with its pill's tone. */
export function setupSummary(checks: SetupCheck[]): { label: string; tone: "danger" | "warn" | "accent" } {
  const failing = checks.filter((c) => c.status === "fail").length;
  if (failing) return { label: t("doctorPage.setupFailing", { count: failing }), tone: "danger" };
  const warnings = checks.filter((c) => c.status === "warn").length;
  if (warnings) return { label: t("doctorPage.setupWarnings", { count: warnings }), tone: "warn" };
  return { label: t("doctorPage.setupAllOk"), tone: "accent" };
}

/** A part's status in words, for its pill. */
export function setupStatus(check: SetupCheck): string {
  return t(check.status === "fail" ? "doctorPage.statusFail" : check.status === "warn" ? "doctorPage.statusWarn" : "doctorPage.statusOk");
}
