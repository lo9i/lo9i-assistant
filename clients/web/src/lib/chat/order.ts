// How conversation lists are ordered: the newest activity first.
import type { Conversation } from "../api/types";

export function newestFirst(a: Conversation, b: Conversation): number {
  return b.updated_at.localeCompare(a.updated_at);
}
