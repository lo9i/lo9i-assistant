// How Chat lays out the conversations: its list as a table or as cards, the cards' order, the conversations the
// conversation page shows together and where, and the one shown full screen. Kept per browser, all but the one full
// screen, which its button or Esc gives back. Pure functions, so the rules are testable without a page.

export type View = "list" | "cards";

/** How the conversation page places its groups of conversations: next to each other as columns, or one above the
 * other as rows. */
export type Arrangement = "side" | "stacked";

/** Conversations together the other way from the groups: stacked in a column, side by side in a row; each one's
 * share of the group (together 1). */
export type Group = { ids: string[]; shares: number[] };

export type Layout = {
  view: View;
  // The cards' order as the user dragged them, by thread id; null until they do: newest activity first.
  order: string[] | null;
  // The conversations the conversation page shows together, in groups along `arrange`, and each group's share of the
  // page that way (together 1). A page split in half with two stacked in one half is two columns, one holding two.
  groups: Group[];
  shares: number[];
  arrange: Arrangement;
  // The card or conversation shown full screen.
  maximized: string | null;
};

/** The most conversations shown together. */
export const MAX_PANES = 3;
// The smallest share a divider drags a conversation, or a group, to.
export const MIN_SHARE = 0.2;

export const initial: Layout = { view: "list", order: null, groups: [], shares: [], arrange: "side", maximized: null };

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

/** Every conversation shown together, group by group. */
export function together(layout: Layout): string[] {
  return layout.groups.flatMap((g) => g.ids);
}

/** The conversations the page shows while `current` is the conversation shown: those it's together with; it alone
 * otherwise, the others coming back when one of them is shown again. */
export function columnsOf(layout: Layout, current: string): string[] {
  const ids = together(layout);
  return ids.includes(current) ? ids : [current];
}

/** The groups the page shows while `current` is the conversation shown, as `columnsOf` says which. */
export function groupsOf(layout: Layout, current: string): Group[] {
  return together(layout).includes(current) ? layout.groups : [{ ids: [current], shares: [1] }];
}

/** `id` beside `current`, the conversation shown: a group of its own after the others it's with, or the two of them.
 * With MAX_PANES already, the last that isn't `current` gives way. */
export function besideOf(layout: Layout, current: string, id: string): Layout {
  if (id === current) return layout;
  const shown = from(layout, current);
  if (together(shown).includes(id)) return shown;
  return atEnd(roomFor(shown, current), id);
}

/** `id`, moved or added, as a group of its own at the end (dropped at the page's end). */
export function atEnd(layout: Layout, id: string): Layout {
  const without = together(layout).includes(id) ? withoutPane(layout, id) : layout;
  const { groups, shares } = without;
  const share = 1 / (groups.length + 1);
  return canonical({
    ...without,
    groups: [...groups, { ids: [id], shares: [1] }],
    shares: [...shares.map((s) => s * (1 - share)), share],
  });
}

/** Without `id`; the others in its group share its room, and an empty group's goes to the other groups. Shown full
 * screen, the layout comes back. */
export function withoutPane(layout: Layout, id: string): Layout {
  const at = locate(layout, id);
  if (at === null) return layout;
  const group = layout.groups[at.group];
  const left = { ids: group.ids.filter((p) => p !== id), shares: normalized(group.shares.filter((_, i) => i !== at.item)) };
  const kept = left.ids.length > 0;
  return canonical({
    ...layout,
    groups: kept ? layout.groups.map((g, i) => (i === at.group ? left : g)) : layout.groups.filter((_, i) => i !== at.group),
    shares: kept ? layout.shares : layout.shares.filter((_, i) => i !== at.group),
    maximized: layout.maximized === id ? null : layout.maximized,
  });
}

/** `next` in the place and share of `id` (/clear in it starts a new conversation there). */
export function replacedPane(layout: Layout, id: string, next: string): Layout {
  if (locate(layout, id) === null || id === next) return layout;
  const shown = together(layout).includes(next) ? withoutPane(layout, next) : layout;
  return {
    ...shown,
    groups: shown.groups.map((g) => ({ ...g, ids: g.ids.map((p) => (p === id ? next : p)) })),
    maximized: layout.maximized === id ? next : shown.maximized,
  };
}

/** `shares` with the divider after `index` dragged by `delta` (a share, positive to the right or down): the two beside
 * it share their room differently, neither below MIN_SHARE. */
export function resized(shares: readonly number[], index: number, delta: number): number[] {
  if (index < 0 || index + 1 >= shares.length) return [...shares];
  const pair = shares[index] + shares[index + 1];
  if (pair < 2 * MIN_SHARE) return [...shares];
  const first = Math.min(Math.max(shares[index] + delta, MIN_SHARE), pair - MIN_SHARE);
  return shares.map((s, i) => (i === index ? first : i === index + 1 ? pair - first : s));
}

/** The divider between groups `index` and `index + 1` dragged by `delta`. */
export function resizedGroups(layout: Layout, index: number, delta: number): Layout {
  return { ...layout, shares: resized(layout.shares, index, delta) };
}

/** The divider after conversation `index` of group `group` dragged by `delta`. */
export function resizedWithin(layout: Layout, group: number, index: number, delta: number): Layout {
  return {
    ...layout,
    groups: layout.groups.map((g, i) => (i === group ? { ...g, shares: resized(g.shares, index, delta) } : g)),
  };
}

/** Where on a conversation something dragged is dropped: the edge it's nearest, which says where it goes. */
export type Edge = "left" | "right" | "top" | "bottom";

/** The edge of `box` the point (`x`, `y`) is nearest, measured as a share of its width or height, so a tall
 * conversation isn't only ever dropped on at its sides. */
export function edgeOf(box: { left: number; top: number; width: number; height: number }, x: number, y: number): Edge {
  const distances: [Edge, number][] = [
    ["left", (x - box.left) / box.width],
    ["right", (box.left + box.width - x) / box.width],
    ["top", (y - box.top) / box.height],
    ["bottom", (box.top + box.height - y) / box.height],
  ];
  return distances.reduce((nearest, next) => (next[1] < nearest[1] ? next : nearest))[0];
}

/** `id`, moved or added, dropped at `edge` of `target`, a conversation shown: it takes that half of `target`'s room.
 * At an edge along the groups it's a group of its own beside `target`'s; across them it joins `target`'s group (a
 * column split in two, stacked; a row, side by side). The last other than `target` gives way past MAX_PANES. */
export function docked(layout: Layout, target: string, id: string, edge: Edge): Layout {
  if (id === target) return layout;
  const shown = from(layout, target);
  const cleared = from(together(shown).includes(id) ? withoutPane(shown, id) : roomFor(shown, target), target);
  const at = locate(cleared, target);
  if (at === null) return layout;
  const after = edge === "right" || edge === "bottom";
  const along = (cleared.arrange === "side") === (edge === "left" || edge === "right");
  return canonical(along ? groupBeside(cleared, id, at.group, after) : intoGroup(cleared, id, at, after));
}

/** Columns become rows and rows columns: side by side, then stacked, each keeping its share. */
export function rearranged(layout: Layout): Layout {
  return { ...layout, arrange: layout.arrange === "side" ? "stacked" : "side" };
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
  const { view, order, groups, shares, arrange } = canonical(layout);
  return JSON.stringify({ view, order, groups, shares, arrange });
}

/** The layout kept as `text`; the initial one for nothing, or for what isn't one (an older or broken record), part
 * by part. One kept before groups (`panes`, `widths`) has each conversation as a group. */
export function parsed(text: string | null): Layout {
  let kept: Record<string, unknown> = {};
  try {
    const value: unknown = JSON.parse(text ?? "null");
    if (value && typeof value === "object" && !Array.isArray(value)) kept = value as Record<string, unknown>;
  } catch {
    return initial;
  }
  return canonical({
    view: kept.view === "cards" ? "cards" : "list",
    order: isStrings(kept.order) ? kept.order : null,
    ...keptGroups(kept),
    arrange: kept.arrange === "stacked" ? "stacked" : "side",
    maximized: null,
  });
}

function keptGroups(kept: Record<string, unknown>): Pick<Layout, "groups" | "shares"> {
  const groups = Array.isArray(kept.groups)
    ? kept.groups.filter((g): g is Group => isStrings(g?.ids)).map((g) => ({ ids: g.ids, shares: numbers(g.shares) }))
    : isStrings(kept.panes)
      ? kept.panes.map((id) => ({ ids: [id], shares: [1] }))
      : [];
  return { groups: distinct(groups), shares: numbers(Array.isArray(kept.groups) ? kept.shares : kept.widths) };
}

/** Each conversation once, MAX_PANES at most, the first kept. */
function distinct(groups: Group[]): Group[] {
  const seen = new Set<string>();
  return groups.map((g) => {
    const ids = g.ids.filter((id) => !seen.has(id) && seen.size < MAX_PANES && seen.add(id));
    return { ids, shares: ids.length === g.ids.length ? g.shares : [] };
  });
}

function numbers(value: unknown): number[] {
  return Array.isArray(value) && value.every((n) => typeof n === "number" && n > 0) ? (value as number[]) : [];
}

function isStrings(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((v) => typeof v === "string");
}

/** `layout` with `target` among the conversations shown together: as it is when it is, else it alone. */
function from(layout: Layout, target: string): Layout {
  if (together(layout).includes(target)) return layout;
  return { ...layout, groups: [{ ids: [target], shares: [1] }], shares: [1] };
}

/** Room for one more: with MAX_PANES shown, the last that isn't `keep` gives way. */
function roomFor(layout: Layout, keep: string): Layout {
  const ids = together(layout);
  if (ids.length < MAX_PANES) return layout;
  return withoutPane(layout, ids.findLast((id) => id !== keep) ?? keep);
}

/** Where `id` is: its group and its place in it. */
function locate(layout: Layout, id: string): { group: number; item: number } | null {
  const group = layout.groups.findIndex((g) => g.ids.includes(id));
  return group < 0 ? null : { group, item: layout.groups[group].ids.indexOf(id) };
}

/** `id` as a group of its own before or after group `at`, taking half of that group's share. */
function groupBeside(layout: Layout, id: string, at: number, after: boolean): Layout {
  const half = layout.shares[at] / 2;
  const index = after ? at + 1 : at;
  const shares = layout.shares.map((s, i) => (i === at ? half : s));
  return {
    ...layout,
    groups: [...layout.groups.slice(0, index), { ids: [id], shares: [1] }, ...layout.groups.slice(index)],
    shares: [...shares.slice(0, index), half, ...shares.slice(index)],
  };
}

/** `id` in group `at.group`, before or after its conversation `at.item`, taking half of that one's share. */
function intoGroup(layout: Layout, id: string, at: { group: number; item: number }, after: boolean): Layout {
  const group = layout.groups[at.group];
  const half = group.shares[at.item] / 2;
  const index = after ? at.item + 1 : at.item;
  const shares = group.shares.map((s, i) => (i === at.item ? half : s));
  const grown = {
    ids: [...group.ids.slice(0, index), id, ...group.ids.slice(index)],
    shares: [...shares.slice(0, index), half, ...shares.slice(index)],
  };
  return { ...layout, groups: layout.groups.map((g, i) => (i === at.group ? grown : g)) };
}

/** One way to write each layout: no empty groups, shares that fit and add up to 1, nothing kept for one conversation
 * alone, and a single group of several written as that many groups the other way. */
function canonical(layout: Layout): Layout {
  const groups = layout.groups
    .map((g, i) => ({ group: { ids: g.ids, shares: fitted(g.shares, g.ids.length) }, share: layout.shares[i] }))
    .filter(({ group }) => group.ids.length > 0);
  if (groups.flatMap(({ group }) => group.ids).length <= 1) return { ...layout, groups: [], shares: [] };
  if (groups.length === 1) {
    const only = groups[0].group;
    return {
      ...layout,
      arrange: layout.arrange === "side" ? "stacked" : "side",
      groups: only.ids.map((id) => ({ ids: [id], shares: [1] })),
      shares: only.shares,
    };
  }
  const shares = groups.map(({ share }) => share);
  return { ...layout, groups: groups.map(({ group }) => group), shares: fitted(shares, groups.length) };
}

/** `shares` adding up to 1, or even ones when they don't fit `count`. */
function fitted(shares: readonly (number | undefined)[], count: number): number[] {
  const known = shares.length === count && shares.every((s) => typeof s === "number" && s > 0);
  return known ? normalized(shares as number[]) : Array.from({ length: count }, () => 1 / count);
}

/** `list` with `id` moved before `before`, or to the end for null or one that isn't there. */
function placed(list: readonly string[], id: string, before: string | null): string[] {
  const rest = list.filter((x) => x !== id);
  const at = before !== null && rest.includes(before) ? rest.indexOf(before) : rest.length;
  return [...rest.slice(0, at), id, ...rest.slice(at)];
}

function normalized(shares: readonly number[]): number[] {
  const total = shares.reduce((a, b) => a + b, 0);
  return total > 0 ? shares.map((s) => s / total) : shares.map(() => 1 / shares.length);
}
