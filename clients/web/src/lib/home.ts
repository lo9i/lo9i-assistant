// Home (core/home/): when each item is, when the page was last updated, and the sections as the editor changes them.
import type { HomeItem, HomeSection } from "./api/types";
import { local } from "./jobs";

const DAY_MS = 24 * 60 * 60 * 1000;

/** The day in `timezone` as YYYY-MM-DD, the format items' dates come in. */
export function dayOf(date: Date, timezone = Intl.DateTimeFormat().resolvedOptions().timeZone): string {
  return new Intl.DateTimeFormat("en-CA", { year: "numeric", month: "2-digit", day: "2-digit", timeZone: timezone }).format(date);
}

/** When an item is, seen from `today`: "09:00", "Tomorrow 21:00", "Fri 24 Oct", or "" for an item without either. */
export function itemWhen(item: Pick<HomeItem, "date" | "time">, today: string): string {
  const time = item.time ?? "";
  const date = item.date ?? "";
  if (!date || date === today) return time || (date ? "Today" : "");
  const day = dayName(date, today);
  return time ? `${day} ${time}` : day;
}

function dayName(date: string, today: string): string {
  const days = Math.round((Date.parse(date) - Date.parse(today)) / DAY_MS);
  if (days === 1) return "Tomorrow";
  if (days === -1) return "Yesterday";
  return new Intl.DateTimeFormat("en-GB", { weekday: "short", day: "2-digit", month: "short", timeZone: "UTC" })
    .format(new Date(date))
    .replace(",", "");
}

/** "Updated 10:32" today, "Updated Wed 21 Oct 18:05" before; "" before the first refresh. */
export function updatedLabel(at: string, now: Date, timezone = Intl.DateTimeFormat().resolvedOptions().timeZone): string {
  if (!at) return "";
  const shown = local(at, timezone);
  const sameDay = dayOf(new Date(at), timezone) === dayOf(now, timezone);
  return `Updated ${sameDay ? shown.slice(-5) : shown}`;
}

/** The sections with `edited` in place of the one with its id, or added at the end when it's new (no id yet). */
export function withSection(sections: HomeSection[], edited: HomeSection): HomeSection[] {
  if (!edited.id) return [...sections, edited];
  return sections.map((s) => (s.id === edited.id ? edited : s));
}

export function withoutSection(sections: HomeSection[], id: string): HomeSection[] {
  return sections.filter((s) => s.id !== id);
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
