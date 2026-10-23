// A conversation's stats as the chat's status bar shows them (GET /conversations/<id>/stats).
import type { ConversationStats } from "./api/types";
import { duration } from "./duration";
import { localTime } from "./health";

/** Like "24 messages · 182k tokens · 37 tools · 2 h ago". */
export function statsLine(stats: ConversationStats, now: string): string {
  const parts = [
    counted(stats.messages, "message"),
    `${compact(stats.input_tokens + stats.output_tokens)} tokens`,
    counted(stats.tool_calls, "tool"),
  ];
  if (stats.last_activity) parts.push(ago(stats.last_activity, now));
  return parts.join(" · ");
}

/** One line per figure, for the line's tooltip. */
export function statsDetail(stats: ConversationStats, timezone = Intl.DateTimeFormat().resolvedOptions().timeZone): string {
  const lines = [
    `Input tokens: ${exact(stats.input_tokens)}`,
    `Output tokens: ${exact(stats.output_tokens)}`,
    `Cache read tokens: ${exact(stats.cache_read_tokens)}`,
    `Model calls: ${exact(stats.model_calls)}`,
    `Tool calls: ${exact(stats.tool_calls)}`,
  ];
  if (stats.started_at) lines.push(`Started: ${localTime(stats.started_at, timezone)}`);
  if (stats.last_activity) lines.push(`Last activity: ${localTime(stats.last_activity, timezone)}`);
  return lines.join("\n");
}

/** Like "950", "4.2k", "182k", "1.3M". */
export function compact(tokens: number): string {
  if (tokens >= 1_000_000) return `${(tokens / 1_000_000).toFixed(1)}M`;
  if (tokens >= 10_000) return `${Math.round(tokens / 1000)}k`;
  return tokens >= 1000 ? `${(tokens / 1000).toFixed(1)}k` : String(tokens);
}

function counted(count: number, noun: string): string {
  return `${count} ${noun}${count === 1 ? "" : "s"}`;
}

function exact(count: number): string {
  return count.toLocaleString("en-US");
}

function ago(at: string, now: string): string {
  const since = duration(at, now);
  return since === "under a minute" ? "just now" : `${since} ago`;
}
