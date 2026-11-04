// When a tool call started, as its card shows it.
import { formatDate } from "../i18n.svelte";

/** The time a call started (`at`, ISO 8601), with its day when that wasn't today, and the whole date and time for its
 * title; null for a call from before that was kept. */
export function callTime(at: string | undefined, now: Date = new Date()): { shown: string; whole: string } | null {
  if (!at) return null;
  const started = new Date(at);
  if (Number.isNaN(started.getTime())) return null;
  const today = started.toDateString() === now.toDateString();
  const time: Intl.DateTimeFormatOptions = { hour: "2-digit", minute: "2-digit" };
  const shown = formatDate(started, today ? time : { ...time, day: "numeric", month: "short" });
  return { shown, whole: formatDate(started, { dateStyle: "full", timeStyle: "medium" }) };
}
