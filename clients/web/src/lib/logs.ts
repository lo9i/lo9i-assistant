// The Logs page's picks and how a followed log's events change what it shows.
import type { LogEntry, LogEvent } from "./api/types";
import { t, type Key } from "./i18n.svelte";

export const LINES = [50, 100, 200, 500];
export const DEFAULT_LINES = 100;
// The value of "All" in the level and component rows.
export const ALL = "";

/** What the page shows after a followed log's event: a page replaces everything, a new entry goes at
 * the bottom, and only the latest `lines` stay. */
export function applyLogEvent(entries: LogEntry[], event: LogEvent, lines: number): LogEntry[] {
  if (event.kind === "page") return event.page.entries;
  return [...entries, event.entry].slice(-lines);
}

/** How a line is tinted: warnings amber, errors red. */
export function tone(level: string): "warn" | "danger" | "" {
  if (level === "WARNING") return "warn";
  return level === "ERROR" || level === "CRITICAL" ? "danger" : "";
}

const LEVELS: Record<string, Key> = {
  DEBUG: "logs.debug",
  INFO: "logs.info",
  WARNING: "logs.warning",
  ERROR: "logs.error",
  CRITICAL: "logs.critical",
};

/** "WARNING" → "Warning". */
export function levelLabel(level: string): string {
  return level in LEVELS ? t(LEVELS[level]) : level.charAt(0) + level.slice(1).toLowerCase();
}

/** One entry as it is written in the file; output that isn't a record has no time, level or logger. */
export function logLine(entry: LogEntry): string {
  const head = entry.level ? `${entry.time} ${entry.level} ${entry.logger}: ` : "";
  return head + entry.message;
}

/** A file's size, for the card's header. */
export function fileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}
