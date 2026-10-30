import { goto } from "$app/navigation";
import { resolve } from "$app/paths";
import { besideOf, columnsOf, type Layout } from "$lib/chat/cardLayout";
import type { ChatSnapshot } from "$lib/chat/controller";
import type { OpenChats } from "$lib/chat/openChats";
import { t } from "$lib/i18n.svelte";
import type { NoticeBoard } from "$lib/notices";

/** Shows `threadId` in Chat, beside the conversations open there; for the inbox, which Chat never shows, the list of
 * conversations instead, and for one that was deleted, a note, staying on the page. */
export async function openConversation(chats: Pick<OpenChats, "show">, notices: NoticeBoard, threadId: string): Promise<void> {
  try {
    const shown = await chats.show(threadId);
    if (shown === "gone") return notices.notify(t("controller.deleted"), "warning");
    await goto(resolve(shown === "shown" ? "/conversations/open" : "/conversations"));
  } catch (e) {
    notices.report(e);
  }
}

/** What a conversation dragged from the sidebar carries, its id: dropped on the conversation page, it opens beside. */
export const CONVERSATION_DRAG = "application/x-lo9i-conversation";

/** Where the conversation page's columns are kept (conversationLayout). */
export type Columns = { readonly current: Layout; change(next: Layout): void };

/** Shows `threadId` in Chat beside the conversation shown there, as columns of the conversation page; alone when none
 * is shown. As `openConversation` for the inbox and for one that was deleted. */
export async function openBeside(
  chats: Pick<OpenChats, "show" | "current">,
  notices: NoticeBoard,
  columns: Columns,
  threadId: string,
): Promise<void> {
  const before = chats.current?.getSnapshot();
  const anchor = before && before.threadId !== before.inboxId ? before.threadId : null;
  try {
    const shown = await chats.show(threadId);
    if (shown === "gone") return notices.notify(t("controller.deleted"), "warning");
    if (shown === "inbox") return void (await goto(resolve("/conversations")));
    if (anchor !== null) columns.change(besideOf(columns.current, anchor, threadId));
    await goto(resolve("/conversations/open"));
  } catch (e) {
    notices.report(e);
  }
}

/** Starts a new conversation and shows it; while the conversation shown is side by side or stacked with others, the
 * new one joins them (the last other giving way past MAX_PANES). */
export async function startNewHere(chats: Pick<OpenChats, "startNew" | "current">, columns: Columns): Promise<void> {
  const before = chats.current?.getSnapshot();
  const split = before !== undefined && columnsOf(columns.current, before.threadId).length > 1;
  const started = (await chats.startNew()).getSnapshot().threadId;
  if (split) columns.change(besideOf(columns.current, before.threadId, started));
}

/** Takes a page about to show `chat` on the inbox, or no chat (none is open), to the list of conversations, in its
 * place in history, so going back doesn't come to it again. Returns whether it did. */
export function leaveInbox(chat: Pick<ChatSnapshot, "threadId" | "inboxId"> | null): boolean {
  if (chat !== null && chat.threadId !== chat.inboxId) return false;
  void goto(resolve("/conversations"), { replaceState: true });
  return true;
}
