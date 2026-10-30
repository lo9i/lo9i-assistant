// Home's Conversations card (core/home/conversations.py): the conversations pinned to Home, or the most recent
// ones while none is.
import type { Conversation } from "./api/types";
import { newestFirst } from "./chat/order";

/** The conversations shown while none is pinned. */
export const RECENT = 5;

/** The pinned conversations still listed, in the order pinned (`pinned` true); with none, the most recent ones that
 * aren't archived. Never the inbox. */
export function homeConversations(listed: readonly Conversation[], pins: readonly string[]): { shown: Conversation[]; pinned: boolean } {
  const byId = new Map(listed.filter((c) => !c.inbox).map((c) => [c.thread_id, c]));
  const found = pins.flatMap((id) => byId.get(id) ?? []);
  if (found.length) return { shown: found, pinned: true };
  const recent = [...byId.values()].filter((c) => !c.archived).sort(newestFirst);
  return { shown: recent.slice(0, RECENT), pinned: false };
}
