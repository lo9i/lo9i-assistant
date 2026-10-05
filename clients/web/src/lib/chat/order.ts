// How conversation lists are ordered: home (the long-running conversation channels write to) first,
// then the newest activity.
import type { Conversation } from "../api/types";

export function homeFirst(a: Conversation, b: Conversation): number {
  return Number(b.home ?? false) - Number(a.home ?? false) || b.updated_at.localeCompare(a.updated_at);
}
