import { goto } from "$app/navigation";
import { resolve } from "$app/paths";
import type { OpenChats } from "$lib/chat/openChats";
import type { NoticeBoard } from "$lib/notices";

/** Shows `threadId` in Chat, beside the conversations open there (the inbox when it's `inboxId`). */
export async function openConversation(chats: OpenChats, notices: NoticeBoard, threadId: string, inboxId = ""): Promise<void> {
  try {
    if (threadId === inboxId) await chats.goInbox();
    else await chats.show(threadId);
    await goto(resolve("/conversations/open"));
  } catch (e) {
    notices.report(e);
  }
}
