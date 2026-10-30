// A conversation's stats as the chat's status bar shows them (GET /conversations/<id>/stats).
import type { ConversationStats } from "./api/types";
import { localTime } from "./health";
import { formatNumber, t } from "./i18n.svelte";

/** One figure of the tooltip, with a note after its value (the cache's share of the input). */
export interface StatsRow {
  label: string;
  value: string;
  note?: string;
}

/** A titled group of the tooltip's figures. */
export interface StatsGroup {
  title: string;
  rows: StatsRow[];
}

/** Like "24 messages · 182k tokens · 37 tools". */
export function statsLine(stats: ConversationStats): string {
  return [
    t("stats.messages", { count: stats.messages }),
    t("stats.tokens", { tokens: compact(stats.input_tokens + stats.output_tokens) }),
    t("stats.tools", { count: stats.tool_calls }),
  ].join(" · ");
}

/** The line's figures alone, for where icons stand for their words: messages, tokens and tools. */
export function statsFigures(stats: ConversationStats): { messages: string; tokens: string; tools: string } {
  return {
    messages: formatNumber(stats.messages),
    tokens: compact(stats.input_tokens + stats.output_tokens),
    tools: formatNumber(stats.tool_calls),
  };
}

/** The line's tooltip: its tokens, its calls and when it started, each group under a title. */
export function statsDetail(stats: ConversationStats, timezone = Intl.DateTimeFormat().resolvedOptions().timeZone): StatsGroup[] {
  const groups: StatsGroup[] = [
    {
      title: t("stats.detail.tokens"),
      rows: [
        { label: t("stats.detail.input"), value: formatNumber(stats.input_tokens) },
        { label: t("stats.detail.cached"), value: formatNumber(stats.cache_read_tokens), note: cacheShare(stats) },
        { label: t("stats.detail.output"), value: formatNumber(stats.output_tokens) },
      ],
    },
    {
      title: t("stats.detail.calls"),
      rows: [
        { label: t("stats.detail.modelCalls"), value: formatNumber(stats.model_calls) },
        { label: t("stats.detail.toolCalls"), value: formatNumber(stats.tool_calls) },
      ],
    },
  ];
  if (stats.started_at) {
    groups.push({
      title: t("stats.detail.time"),
      rows: [{ label: t("stats.detail.started"), value: localTime(stats.started_at, timezone) }],
    });
  }
  return groups;
}

/** How much of the input the provider read from its cache, like "70%"; none before any input. */
function cacheShare(stats: ConversationStats): string | undefined {
  if (!stats.input_tokens) return undefined;
  return formatNumber(stats.cache_read_tokens / stats.input_tokens, { style: "percent", maximumFractionDigits: 0 });
}

/** Like "950", "4.2k", "182k", "1.3M"; in Spanish "4,2k". */
export function compact(tokens: number): string {
  const one = (n: number) => formatNumber(n, { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  if (tokens >= 1_000_000) return `${one(tokens / 1_000_000)}M`;
  if (tokens >= 10_000) return `${Math.round(tokens / 1000)}k`;
  return tokens >= 1000 ? `${one(tokens / 1000)}k` : String(tokens);
}
