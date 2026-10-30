import { t } from "./i18n.svelte";

/** How long between two times, roughly and briefly: "< 1 min", "12 min", "2 h 5 min", "3 days". */
export function duration(from: string, to: string): string {
  const minutes = minutesBetween(from, to);
  if (minutes < 1) return t("duration.underAMinute");
  if (minutes < 60) return t("duration.minutes", { minutes });
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return minutes % 60 ? t("duration.hoursMinutes", { hours, minutes: minutes % 60 }) : t("duration.hours", { hours });
  return t("duration.days", { count: Math.floor(hours / 24) });
}

/** "just now", "12 min ago", "3 days ago". */
export function ago(at: string, now: string): string {
  return minutesBetween(at, now) < 1 ? t("duration.justNow") : t("duration.ago", { since: duration(at, now) });
}

function minutesBetween(from: string, to: string): number {
  return Math.floor((new Date(to).getTime() - new Date(from).getTime()) / 60000);
}
