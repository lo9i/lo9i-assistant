// How Chat lays out the conversations: its list as a table or as cards, the cards' order, the conversations the
// conversation page shows side by side as columns with each one's share of the width, and the one shown full screen.
// Kept per browser, all but the one full screen, which its button or Esc gives back. Pure functions, so the rules are
// testable without a page.

export type View = "list" | "cards";

export type Layout = {
  view: View;
  // The cards' order as the user dragged them, by thread id; null until they do: newest activity first.
  order: string[] | null;
  // The conversations side by side, left to right, and each one's share of the width (together 1).
  panes: string[];
  widths: number[];
  // The card or pane shown full screen.
  maximized: string | null;
};

export const MAX_PANES = 3;
// The narrowest a divider drags a pane to, as a share of the width.
export const MIN_WIDTH = 0.2;

export const initial: Layout = { view: "list", order: null, panes: [], widths: [], maximized: null };

/** The cards in order: those the user never placed (new since they last dragged one) first, newest first, then the
 * user's order. `newestFirst` are the conversations listed; one in the order that's gone isn't shown. */
export function ordered(newestFirst: readonly string[], order: readonly string[] | null): string[] {
  if (order === null) return [...newestFirst];
  const listed = new Set(newestFirst);
  const placed = order.filter((id) => listed.has(id));
  const known = new Set(placed);
  return [...newestFirst.filter((id) => !known.has(id)), ...placed];
}

/** What a drop on `target`, past its middle when `after`, puts things before: `target`, or the one after it (null at
 * the end). */
export function beforeOf(list: readonly string[], target: string, after: boolean): string | null {
  if (!after) return target;
  return list[list.indexOf(target) + 1] ?? null;
}

/** `shown`, the cards as ordered, with `id` moved before `before` (to the end for null). */
export function movedCard(layout: Layout, shown: readonly string[], id: string, before: string | null): Layout {
  return { ...layout, order: placed(shown, id, before) };
}

/** Back to newest activity first. */
export function unordered(layout: Layout): Layout {
  return { ...layout, order: null };
}

/** `id` side by side with the others, before `before` (at the end for null or one that isn't there). With
 * MAX_PANES already, the last of them gives way. The new pane gets an even share; the others keep their proportions. */
export function withPane(layout: Layout, id: string, before: string | null = null): Layout {
  if (layout.panes.includes(id)) return movedPane(layout, id, before);
  const { panes, widths } = fitted(layout);
  const kept = panes.length >= MAX_PANES ? panes.slice(0, MAX_PANES - 1) : panes;
  const share = 1 / (kept.length + 1);
  const scaled = normalized(widths.slice(0, kept.length)).map((w) => w * (1 - share));
  const at = before !== null && kept.includes(before) ? kept.indexOf(before) : kept.length;
  return {
    ...layout,
    panes: [...kept.slice(0, at), id, ...kept.slice(at)],
    widths: [...scaled.slice(0, at), share, ...scaled.slice(at)],
  };
}

/** The columns the conversation page shows while `current` is the conversation shown: those side by side when it's
 * one of them; it alone otherwise, the others coming back when one of them is shown again. */
export function columnsOf(layout: Layout, current: string): string[] {
  return layout.panes.includes(current) ? layout.panes : [current];
}

/** `id` beside `current`, the conversation shown: added to the columns it's in, or the two of them as new columns.
 * With MAX_PANES already, the last that isn't `current` gives way. */
export function besideOf(layout: Layout, current: string, id: string): Layout {
  if (id === current) return layout;
  const shown: Layout = layout.panes.includes(current) ? layout : { ...layout, panes: [current], widths: [1] };
  if (shown.panes.includes(id)) return shown;
  if (shown.panes.length < MAX_PANES) return withPane(shown, id);
  const giving = shown.panes.findLast((p) => p !== current) ?? current;
  return withPane(withoutPane(shown, giving), id);
}

/** Without the pane on `id`; the others share its width. Shown full screen, the layout comes back. */
export function withoutPane(layout: Layout, id: string): Layout {
  const { panes, widths } = fitted(layout);
  const at = panes.indexOf(id);
  if (at < 0) return layout;
  return {
    ...layout,
    panes: panes.filter((p) => p !== id),
    widths: normalized(widths.filter((_, i) => i !== at)),
    maximized: layout.maximized === id ? null : layout.maximized,
  };
}

/** The pane on `id` moved before `before` (to the end for null), keeping its width. */
export function movedPane(layout: Layout, id: string, before: string | null): Layout {
  const { panes, widths } = fitted(layout);
  if (!panes.includes(id)) return layout;
  const order = placed(panes, id, before);
  return { ...layout, panes: order, widths: order.map((p) => widths[panes.indexOf(p)]) };
}

/** The pane on `id` shows `next` instead, in its place and width (/clear in it starts a new conversation there). */
export function replacedPane(layout: Layout, id: string, next: string): Layout {
  if (!layout.panes.includes(id) || id === next) return layout;
  const shown = withoutPane(layout, next);
  return { ...shown, panes: shown.panes.map((p) => (p === id ? next : p)), maximized: layout.maximized === id ? next : shown.maximized };
}

/** `widths` with the divider after pane `index` dragged by `delta` (a share of the width, positive to the right):
 * the two panes beside it share their width differently, neither narrower than MIN_WIDTH. */
export function resized(widths: readonly number[], index: number, delta: number): number[] {
  if (index < 0 || index + 1 >= widths.length) return [...widths];
  const pair = widths[index] + widths[index + 1];
  if (pair < 2 * MIN_WIDTH) return [...widths];
  const left = Math.min(Math.max(widths[index] + delta, MIN_WIDTH), pair - MIN_WIDTH);
  return widths.map((w, i) => (i === index ? left : i === index + 1 ? pair - left : w));
}

/** Full screen for `id`, or back to the layout when it already is. */
export function toggledMax(layout: Layout, id: string): Layout {
  return { ...layout, maximized: layout.maximized === id ? null : id };
}

export function restored(layout: Layout): Layout {
  return layout.maximized === null ? layout : { ...layout, maximized: null };
}

/** What's kept of `layout`: everything but the one full screen. */
export function serialized(layout: Layout): string {
  const { view, order, panes, widths } = fitted(layout);
  return JSON.stringify({ view, order, panes, widths });
}

/** The layout kept as `text`; the initial one for nothing, or for what isn't one (an older or broken record), part
 * by part. */
export function parsed(text: string | null): Layout {
  let kept: Record<string, unknown> = {};
  try {
    const value: unknown = JSON.parse(text ?? "null");
    if (value && typeof value === "object" && !Array.isArray(value)) kept = value as Record<string, unknown>;
  } catch {
    return initial;
  }
  const panes = isStrings(kept.panes) ? [...new Set(kept.panes)].slice(0, MAX_PANES) : [];
  const widths = Array.isArray(kept.widths) && kept.widths.every((w) => typeof w === "number" && w > 0) ? (kept.widths as number[]) : [];
  return fitted({
    view: kept.view === "cards" ? "cards" : "list",
    order: isStrings(kept.order) ? kept.order : null,
    panes,
    widths,
    maximized: null,
  });
}

function isStrings(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((v) => typeof v === "string");
}

/** `list` with `id` moved before `before`, or to the end for null or one that isn't there. */
function placed(list: readonly string[], id: string, before: string | null): string[] {
  const rest = list.filter((x) => x !== id);
  const at = before !== null && rest.includes(before) ? rest.indexOf(before) : rest.length;
  return [...rest.slice(0, at), id, ...rest.slice(at)];
}

/** One width per pane, together 1: even shares when they don't match the panes. */
function fitted(layout: Layout): Layout {
  const widths = layout.widths.length === layout.panes.length ? normalized(layout.widths) : layout.panes.map(() => 1 / layout.panes.length);
  return { ...layout, widths };
}

function normalized(widths: readonly number[]): number[] {
  const total = widths.reduce((a, b) => a + b, 0);
  return total > 0 ? widths.map((w) => w / total) : widths.map(() => 1 / widths.length);
}
