// Home's Conversations card (core/home/conversations.py): the most recent conversations.
import type { Conversation } from "./api/types";
import { newestFirst } from "./chat/order";

/** The conversations shown. */
export const RECENT = 5;

/** The most recent ones, newest first, never the inbox nor an archived one. */
export function homeConversations(listed: readonly Conversation[]): Conversation[] {
  return listed
    .filter((c) => !c.inbox && !c.archived)
    .sort(newestFirst)
    .slice(0, RECENT);
}
