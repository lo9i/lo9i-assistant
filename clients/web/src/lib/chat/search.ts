// Searching the list of conversations: by title as it's typed, and by what was said in them once the daemon answers.
import type { Conversation } from "../api/types";

/** The shortest search the daemon looks for in messages: one letter starts most of their words. */
export const MESSAGE_SEARCH_MIN = 2;

/** What the daemon is asked to look for in messages for `query`; "" for nothing. */
export function messageSearch(query: string): string {
  const words = query.trim();
  return words.length >= MESSAGE_SEARCH_MIN ? words : "";
}

/** The conversations whose title holds `query`, or whose messages the daemon found it in (`containing`, ids). */
export function matching(conversations: readonly Conversation[], query: string, containing: readonly string[]): Conversation[] {
  const words = query.trim().toLowerCase();
  if (!words) return [...conversations];
  const found = new Set(messageSearch(words) ? containing : []);
  return conversations.filter((c) => c.title.toLowerCase().includes(words) || found.has(c.thread_id));
}
