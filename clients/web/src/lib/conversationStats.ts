// A conversation's stats as the chat's status bar shows them (GET /conversations/<id>/stats).
import type { ConversationStats } from "./api/types";
import { ago } from "./duration";
import { localTime } from "./health";
import { formatNumber, t } from "./i18n.svelte";

/** Like "24 messages · 182k tokens · 37 tools · 2 h ago". */
export function statsLine(stats: ConversationStats, now: string): string {
  const parts = [
    t("stats.messages", { count: stats.messages }),
    t("stats.tokens", { tokens: compact(stats.input_tokens + stats.output_tokens) }),
    t("stats.tools", { count: stats.tool_calls }),
  ];
  if (stats.last_activity) parts.push(ago(stats.last_activity, now));
  return parts.join(" · ");
}

/** The line's figures alone, for where icons stand for their words: messages, tokens, tools, and how long ago. */
export function statsFigures(stats: ConversationStats, now: string): { messages: string; tokens: string; tools: string; ago: string } {
  return {
    messages: formatNumber(stats.messages),
    tokens: compact(stats.input_tokens + stats.output_tokens),
    tools: formatNumber(stats.tool_calls),
    ago: stats.last_activity ? ago(stats.last_activity, now) : "",
  };
}

/** One line per figure, for the line's tooltip. */
export function statsDetail(stats: ConversationStats, timezone = Intl.DateTimeFormat().resolvedOptions().timeZone): string {
  const lines = [
    t("stats.inputTokens", { count: formatNumber(stats.input_tokens) }),
    t("stats.outputTokens", { count: formatNumber(stats.output_tokens) }),
    t("stats.cacheReadTokens", { count: formatNumber(stats.cache_read_tokens) }),
    t("stats.modelCalls", { count: formatNumber(stats.model_calls) }),
    t("stats.toolCalls", { count: formatNumber(stats.tool_calls) }),
  ];
  if (stats.started_at) lines.push(t("stats.started", { when: localTime(stats.started_at, timezone) }));
  if (stats.last_activity) lines.push(t("stats.lastActivity", { when: localTime(stats.last_activity, timezone) }));
  return lines.join("\n");
}

/** Like "950", "4.2k", "182k", "1.3M"; in Spanish "4,2k". */
export function compact(tokens: number): string {
  const one = (n: number) => formatNumber(n, { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  if (tokens >= 1_000_000) return `${one(tokens / 1_000_000)}M`;
  if (tokens >= 10_000) return `${Math.round(tokens / 1000)}k`;
  return tokens >= 1000 ? `${one(tokens / 1000)}k` : String(tokens);
}
