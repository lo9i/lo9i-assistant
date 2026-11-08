// The parts of the context a new conversation starts with (core/doctor/context.py), drawn as a ring: largest first,
// each an arc of its share of what the context starts with, and numbered with its share of the model's whole window.
import type { ContextItem, ContextPart } from "./api/types";
import { formatNumber } from "./i18n.svelte";

export type Arc = { name: string; tokens: number; share: number; start: number; length: number };

/** The parts with tokens, largest first, each with its share of the model's `window` (of the total while the window
 * isn't known) and where its arc starts and how long it is, as fractions of the ring. */
export function arcs(parts: ContextPart[], window: number): Arc[] {
  const sized = parts.filter((p) => p.tokens > 0).sort((a, b) => b.tokens - a.tokens);
  const total = sized.reduce((sum, p) => sum + p.tokens, 0);
  let start = 0;
  return sized.map((p) => {
    const length = p.tokens / total;
    const arc = { name: p.name, tokens: p.tokens, share: p.tokens / (window || total), start, length };
    start += length;
    return arc;
  });
}

// Below this a share shows as "<0.01%", which says it's there without a row of zeros.
const TINY = 0.0001;

/** Like "42%", "0.4%" or "0.04%": as many decimals as a small share needs to show. */
export function percent(share: number): string {
  if (share > 0 && share < TINY) return `<${formatNumber(TINY, { style: "percent", maximumFractionDigits: 2 })}`;
  const decimals = share < 0.001 ? 2 : share < 0.01 ? 1 : 0;
  return formatNumber(share, { style: "percent", maximumFractionDigits: decimals });
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

/** `share`: of the model's window; `scale`: against the largest item, for its bar. */
export type Share = ContextItem & { share: number; scale: number };

/** What the part named `name` lists, largest first, each with its share of the model's `window` (of the part while
 * the window isn't known). */
export function itemsOf(parts: ContextPart[], name: string, window: number): Share[] {
  const part = parts.find((p) => p.name === name);
  if (!part?.tokens) return [];
  const items = [...(part.items ?? [])].sort((a, b) => b.tokens - a.tokens);
  const largest = items[0]?.tokens || 1;
  return items.map((item) => ({ ...item, share: item.tokens / (window || part.tokens), scale: item.tokens / largest }));
}
