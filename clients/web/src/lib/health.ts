// Failures of MCP servers and skills (core/health.py), as the pages show them.
import type { Failing, SignedOut } from "./api/types";
import { t } from "./i18n.svelte";
import { local } from "./jobs";

export type Health = { failures?: number; failure?: string; failed_at?: string };

/** Like "Failed 3 times in a row. Last, Sat 03 Oct 14:00: exit code: 1", or "" while it works. */
export function failures(health: Health, timezone = Intl.DateTimeFormat().resolvedOptions().timeZone): string {
  const count = health.failures ?? 0;
  if (!count) return "";
  return t("health.failures", { count, when: localTime(health.failed_at ?? "", timezone), failure: health.failure ?? "" });
}

/** A time in this browser's time zone, like "Sat 03 Oct 14:00". */
export function localTime(timestamp: string, timezone = Intl.DateTimeFormat().resolvedOptions().timeZone): string {
  return local(timestamp, timezone);
}

/** The alert for a `failing` bus event. */
export function failingNotice(event: Failing): string {
  const values = { name: event.name, error: event.error };
  return event.area === "mcp" ? t("health.serverFailing", values) : t("health.skillFailing", values);
}

/** The alert for a `signed_out` bus event. */
export function signedOutNotice(event: SignedOut): string {
  return t("health.signedOut", { name: event.name });
}
