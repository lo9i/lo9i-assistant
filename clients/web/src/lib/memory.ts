import { t, type Key } from "./i18n.svelte";

// The profile's sections (core/memory/profile.py).
const SECTIONS: Record<string, Key> = {
  about: "memory.sections.about",
  people: "memory.sections.people",
  how_to_reply: "memory.sections.howToReply",
  routine: "memory.sections.routine",
  goals: "memory.sections.goals",
  interests: "memory.sections.interests",
  dislikes: "memory.sections.dislikes",
  work: "memory.sections.work",
};

/** A profile section's key as a heading: "how_to_reply" → "How to reply". */
export function sectionLabel(section: string): string {
  if (section in SECTIONS) return t(SECTIONS[section]);
  return section.charAt(0).toUpperCase() + section.slice(1).replace(/_/g, " ");
}

/** A saved memory as the memory page lists it: its text and when it's from. */
export type MemoryItem = { id: string; text: string; when: string };

/** The items whose text has every word of `query`, ignoring case; all of them for an empty query. */
export function matching(items: MemoryItem[], query: string): MemoryItem[] {
  const words = query.toLowerCase().split(/\s+/).filter(Boolean);
  return items.filter((item) => words.every((word) => item.text.toLowerCase().includes(word)));
}

/** The sections with `name` dragged before or after `target`; unchanged when either isn't there, or it's dropped on
 * itself. */
export function placed(order: string[], name: string, target: string, after: boolean): string[] {
  if (name === target || !order.includes(name) || !order.includes(target)) return order;
  const rest = order.filter((section) => section !== name);
  const at = rest.indexOf(target) + (after ? 1 : 0);
  return [...rest.slice(0, at), name, ...rest.slice(at)];
}

/** The sections with `name` moved one place earlier (-1) or later (1), from the keyboard; unchanged at either end. */
export function stepped(order: string[], name: string, by: -1 | 1): string[] {
  const from = order.indexOf(name);
  const to = from + by;
  if (from < 0 || to < 0 || to >= order.length) return order;
  const result = [...order];
  [result[from], result[to]] = [result[to], result[from]];
  return result;
}
