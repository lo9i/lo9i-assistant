// What "Open beside" offers on the conversation page: the conversations to show next to the one shown.
import type { Conversation } from "../api/types";
import { newestFirst } from "./order";
import { matching } from "./search";

/** The conversations whose title holds `query`, newest activity first, but those shown already and the inbox. */
export function besideChoices(listed: readonly Conversation[], shown: readonly string[], query: string): Conversation[] {
  const left = listed.filter((c) => !c.inbox && !shown.includes(c.thread_id));
  return matching(left, query, []).sort(newestFirst);
}
