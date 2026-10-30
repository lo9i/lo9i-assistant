// Home (core/home/): when each item is, its link, how much of a card shows, when the page was last updated, and the
// sections as the editor changes them.
import type { HomeItem, HomeSection } from "./api/types";
import { language, t } from "./i18n.svelte";
import { local } from "./jobs";

const DAY_MS = 24 * 60 * 60 * 1000;
/** The widest a card can be: the columns Home has room for at its widest (MAX_COLUMNS in core/home/model.py). */
export const MAX_COLUMNS = 4;
/** More items than this make a busy card: two columns wide, its list scrolling past about this many. */
export const BUSY_ITEMS = 5;
/** The Conversations card's id (CONVERSATIONS in core/home/sections.py): the app draws it live from the
 * conversations instead of from its result. */
export const CONVERSATIONS = "conversations";
// An address written in the subtitle, with the separator before it, for results built before items had a url.
const URL_IN_TEXT = /\s*(?:[·|,;-]\s*)?(https?:\/\/\S+)/g;

/** The day in `timezone` as YYYY-MM-DD, the format items' dates come in. */
export function dayOf(date: Date, timezone = Intl.DateTimeFormat().resolvedOptions().timeZone): string {
  return new Intl.DateTimeFormat("en-CA", { year: "numeric", month: "2-digit", day: "2-digit", timeZone: timezone }).format(date);
}

/** When an item is, seen from `today`: "09:00", "Tomorrow 21:00", "Fri 24 Oct", or "" for an item without either. */
export function itemWhen(item: Pick<HomeItem, "date" | "time">, today: string): string {
  const time = item.time ?? "";
  const date = item.date ?? "";
  if (!date || date === today) return time || (date ? t("home.today") : "");
  const day = dayName(date, today);
  return time ? `${day} ${time}` : day;
}

function dayName(date: string, today: string): string {
  const days = Math.round((Date.parse(date) - Date.parse(today)) / DAY_MS);
  if (days === 1) return t("home.tomorrow");
  if (days === -1) return t("home.yesterday");
  // English as the app writes dates, the day before the month.
  const locale = language.locale === "en" ? "en-GB" : language.locale;
  return new Intl.DateTimeFormat(locale, { weekday: "short", day: "2-digit", month: "short", timeZone: "UTC" })
    .format(new Date(date))
    .replace(",", "");
}

/** The subtitle without the addresses written in it, and the item's address: its url, or the first one the
 * subtitle had; "" for none. */
export function linked(item: Pick<HomeItem, "subtitle" | "url">): { subtitle: string; url: string } {
  const found = [...item.subtitle.matchAll(URL_IN_TEXT)];
  const subtitle = item.subtitle.replace(URL_IN_TEXT, "").trim();
  return { subtitle, url: item.url || (found[0]?.[1] ?? "") };
}

/** A busy card is worth two columns where the page has them. */
export function isWide(items: unknown[]): boolean {
  return items.length > BUSY_ITEMS;
}

/** The columns a card spans where the page has them: the width the user gave it, or two for a busy one. */
export function cardColumns(section: Pick<HomeSection, "columns">, items: unknown[]): number {
  return section.columns || (isWide(items) ? 2 : 1);
}

/** The columns a card dragged to `width` pixels snaps to, in a grid of `column`-pixel columns `gap` apart, with
 * `available` of them. */
export function snappedColumns(width: number, column: number, gap: number, available: number): number {
  const columns = Math.round((width + gap) / (column + gap));
  return Math.max(1, Math.min(columns, available, MAX_COLUMNS));
}

/** The columns each card takes on a page `available` columns wide, the cards in their saved order: each as many as
 * it asks for (`spans`) that the page has, row after row in order. A card that doesn't fit in what its row has left
 * starts the next row, and the card before it widens to fill its row, so no card moves up into a hole and the page
 * shows them in the order Move up and Move down change. The last row keeps its cards' widths. */
export function packed(spans: number[], available: number): number[] {
  const columns = Math.max(1, available);
  const placed: number[] = [];
  let used = 0;
  for (const span of spans) {
    const wide = Math.max(1, Math.min(span, columns));
    if (used + wide > columns) {
      placed[placed.length - 1] += columns - used;
      used = 0;
    }
    placed.push(wide);
    used += wide;
  }
  return placed;
}

/** "Updated 10:32" today, "Updated Wed 21 Oct 18:05" before; "" before the first refresh. */
export function updatedLabel(at: string, now: Date, timezone = Intl.DateTimeFormat().resolvedOptions().timeZone): string {
  if (!at) return "";
  const shown = local(at, timezone);
  const sameDay = dayOf(new Date(at), timezone) === dayOf(now, timezone);
  return t("home.updated", { when: sameDay ? shown.slice(-5) : shown });
}

/** The sections with `edited` in place of the one with its id, or added at the end when it's new (no id yet). */
export function withSection(sections: HomeSection[], edited: HomeSection): HomeSection[] {
  if (!edited.id) return [...sections, edited];
  return sections.map((s) => (s.id === edited.id ? edited : s));
}

export function withoutSection(sections: HomeSection[], id: string): HomeSection[] {
  return sections.filter((s) => s.id !== id);
}

/** The Conversations card added at the end, titled `title`, unless Home has it. The daemon gives it its own text
 * (a section built by code). */
export function withConversations(sections: HomeSection[], title: string): HomeSection[] {
  if (sections.some((s) => s.id === CONVERSATIONS)) return sections;
  return [...sections, { id: CONVERSATIONS, title, prompt: title, plugins: [], columns: 0 }];
}

/** The section with its card `columns` wide. */
export function withColumns(sections: HomeSection[], id: string, columns: number): HomeSection[] {
  return sections.map((s) => (s.id === id ? { ...s, columns } : s));
}

/** The section moved one place up (-1) or down (1); unchanged at either end. */
export function moved(sections: HomeSection[], id: string, by: -1 | 1): HomeSection[] {
  const from = sections.findIndex((s) => s.id === id);
  const to = from + by;
  if (from < 0 || to < 0 || to >= sections.length) return sections;
  const result = [...sections];
  [result[from], result[to]] = [result[to], result[from]];
  return result;
}

/** The section dragged before the one with id `before` (to the end for null); unchanged for one that isn't there. */
export function movedBefore(sections: HomeSection[], id: string, before: string | null): HomeSection[] {
  const section = sections.find((s) => s.id === id);
  if (!section || before === id) return sections;
  const rest = sections.filter((s) => s !== section);
  const at = before === null ? rest.length : rest.findIndex((s) => s.id === before);
  if (at < 0) return sections;
  return [...rest.slice(0, at), section, ...rest.slice(at)];
}

type Visibility = Pick<Document, "visibilityState" | "addEventListener" | "removeEventListener">;

/** Calls `shown` when the page is visible (now, and each time it shows again) and `hidden` when it stops being,
 * including when the returned function stops following it. */
export function whileVisible(doc: Visibility, shown: () => void, hidden: () => void): () => void {
  let visible = false;
  const follow = (): void => {
    const now = doc.visibilityState === "visible";
    if (now === visible) return;
    visible = now;
    (now ? shown : hidden)();
  };
  follow();
  doc.addEventListener("visibilitychange", follow);
  return () => {
    doc.removeEventListener("visibilitychange", follow);
    if (visible) hidden();
  };
}
