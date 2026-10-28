// What the sidebar lists under Chat: the conversations open in this tab, then every other one with
// something working in it (a reply, a coding task), whoever started it. Never the inbox: it isn't a
// conversation of its own, and Chat's page opens it.
import type { Conversation } from "../api/types";
import type { OpenChatsSnapshot } from "./openChats";

export type OpenItem = {
  // The open conversation's key; null for one working elsewhere that isn't open here.
  key: string | null;
  threadId: string;
  title: string;
  // The one shown.
  active: boolean;
  running: boolean;
  // A question or approval waits for the user.
  waiting: boolean;
};

/** `working` are the conversations with a reply or a task running anywhere. */
export function openList(
  open: Pick<OpenChatsSnapshot, "chats" | "activeKey">,
  conversations: Conversation[],
  working: string[],
): OpenItem[] {
  const busy = new Set(working);
  const titled = (threadId: string) => conversations.find((c) => c.thread_id === threadId)?.title || "New conversation";
  const opened = open.chats
    .filter(({ state }) => state.threadId !== state.inboxId)
    .map(({ key, state }) => ({
      key,
      threadId: state.threadId,
      title: titled(state.threadId),
      active: key === open.activeKey,
      running: state.busy || state.mirroring || busy.has(state.threadId),
      waiting: state.approval !== null,
    }));
  const inbox = new Set([...open.chats.map((c) => c.state.inboxId), ...conversations.filter((c) => c.inbox).map((c) => c.thread_id)]);
  const elsewhere = conversations
    .filter((c) => busy.has(c.thread_id) && !inbox.has(c.thread_id) && !opened.some((o) => o.threadId === c.thread_id))
    .map((c) => ({
      key: null,
      threadId: c.thread_id,
      title: titled(c.thread_id),
      active: false,
      running: true,
      waiting: false,
    }));
  return [...opened, ...elsewhere];
}
