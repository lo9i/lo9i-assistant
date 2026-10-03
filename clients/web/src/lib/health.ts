// Failures of MCP servers and skills (core/health.py), as the pages show them.
import type { Failing } from "./api/types";
import { local } from "./jobs";

export type Health = { failures?: number; failure?: string; failed_at?: string };

/** Like "Failed 3 times in a row. Last, Sat 03 Oct 14:00: exit code: 1", or "" while it works. */
export function failures(health: Health, timezone = Intl.DateTimeFormat().resolvedOptions().timeZone): string {
  const count = health.failures ?? 0;
  if (!count) return "";
  const times = count === 1 ? "Failed once" : `Failed ${count} times in a row`;
  return `${times}. Last, ${localTime(health.failed_at ?? "", timezone)}: ${health.failure}`;
}

/** A time in this browser's time zone, like "Sat 03 Oct 14:00". */
export function localTime(timestamp: string, timezone = Intl.DateTimeFormat().resolvedOptions().timeZone): string {
  return local(timestamp, timezone);
}

/** The alert for a `failing` bus event. */
export function failingNotice(event: Failing): string {
  const what = event.area === "mcp" ? "MCP server" : "skill";
  return `The ${what} ${event.name} keeps failing: ${event.error}. It's listed in Alerts.`;
}
