// What the sidebar lists under Chat: the conversations open in this tab, then every other one with
// something working in it (a reply, a coding task), whoever started it.
import type { Conversation } from "../api/types";
import type { OpenChatsSnapshot } from "./openChats";

export type OpenItem = {
  // The open conversation's key; null for one working elsewhere that isn't open here.
  key: string | null;
  threadId: string;
  title: string;
  inbox: boolean;
  // The one shown.
  active: boolean;
  running: boolean;
  // A question or approval waits for the user.
  waiting: boolean;
};

/** `working` are the conversations with a reply or a task running anywhere. */
export function openList(open: OpenChatsSnapshot, conversations: Conversation[], working: string[]): OpenItem[] {
  const busy = new Set(working);
  const titled = (threadId: string, inbox: boolean) =>
    inbox ? "Inbox" : conversations.find((c) => c.thread_id === threadId)?.title || "New conversation";
  const opened = open.chats.map(({ key, state }) => {
    const inbox = state.threadId === state.inboxId;
    return {
      key,
      threadId: state.threadId,
      title: titled(state.threadId, inbox),
      inbox,
      active: key === open.activeKey,
      running: state.busy || state.mirroring || busy.has(state.threadId),
      waiting: state.approval !== null,
    };
  });
  const elsewhere = conversations
    .filter((c) => busy.has(c.thread_id) && !opened.some((o) => o.threadId === c.thread_id))
    .map((c) => ({
      key: null,
      threadId: c.thread_id,
      title: titled(c.thread_id, c.inbox ?? false),
      inbox: c.inbox ?? false,
      active: false,
      running: true,
      waiting: false,
    }));
  return [...opened, ...elsewhere];
}
