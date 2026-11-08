// The parts of the context a new conversation starts with (core/doctor/context.py), drawn as a ring: largest first,
// each an arc of its share of the total.
import type { ContextItem, ContextPart } from "./api/types";
import { formatNumber } from "./i18n.svelte";

export type Arc = { name: string; tokens: number; share: number; start: number; length: number };

/** The parts with tokens, largest first, each with its share of the total and where its arc starts and how long it
 * is, as fractions of the ring. */
export function arcs(parts: ContextPart[]): Arc[] {
  const sized = parts.filter((p) => p.tokens > 0).sort((a, b) => b.tokens - a.tokens);
  const total = sized.reduce((sum, p) => sum + p.tokens, 0);
  let start = 0;
  return sized.map((p) => {
    const share = p.tokens / total;
    const arc = { name: p.name, tokens: p.tokens, share, start, length: share };
    start += share;
    return arc;
  });
}

/** Like "42%", or "0.4%" for a part too small to round to a whole one. */
export function percent(share: number): string {
  return formatNumber(share, { style: "percent", maximumFractionDigits: share < 0.01 ? 1 : 0 });
}

/** How strong the `rank`th of `count` arcs is coloured, from 100 (the largest) down to 0 (the smallest). */
export function strength(rank: number, count: number): number {
  return count > 1 ? Math.round(100 - (100 * rank) / (count - 1)) : 100;
}

/** The `rank`th of `count` arcs' colour, between the theme's strong and weak shades of the brand's teal-gray
 * (`--ring-strong`, `--ring-weak`, set by ContextBreakdown). */
export function shade(rank: number, count: number): string {
  return `color-mix(in oklab, var(--ring-strong) ${strength(rank, count)}%, var(--ring-weak))`;
}

export type Share = ContextItem & { share: number };

/** What the part named `name` lists, largest first, each with its share of the part. */
export function itemsOf(parts: ContextPart[], name: string): Share[] {
  const part = parts.find((p) => p.name === name);
  if (!part?.tokens) return [];
  const items = [...(part.items ?? [])].sort((a, b) => b.tokens - a.tokens);
  return items.map((item) => ({ ...item, share: item.tokens / part.tokens }));
}
