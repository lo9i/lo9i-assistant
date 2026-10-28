import { goto } from "$app/navigation";
import { resolve } from "$app/paths";
import type { ChatSnapshot } from "$lib/chat/controller";
import type { OpenChats } from "$lib/chat/openChats";
import type { NoticeBoard } from "$lib/notices";

/** Shows `threadId` in Chat, beside the conversations open there; for the inbox, which Chat never shows, the list of
 * conversations instead. */
export async function openConversation(chats: Pick<OpenChats, "show">, notices: NoticeBoard, threadId: string): Promise<void> {
  try {
    const shown = await chats.show(threadId);
    await goto(resolve(shown ? "/conversations/open" : "/conversations"));
  } catch (e) {
    notices.report(e);
  }
}

/** Takes a page about to show `chat` on the inbox to the list of conversations, in its place in history, so going
 * back doesn't come to it again. Returns whether it did. */
export function leaveInbox(chat: Pick<ChatSnapshot, "threadId" | "inboxId">): boolean {
  if (chat.threadId !== chat.inboxId) return false;
  void goto(resolve("/conversations"), { replaceState: true });
  return true;
}
