// The chats of a browser tab: the conversations open in Chat and the quick buttons' (voice, text). Each joins as
// it's made, before its history loads, so run events reach it from then on (it shows them once its history has).
// One of them asks what a conversation's run stopped for, so the user sees one dialog and the run goes on there.
import type { ChatController } from "./controller";

/** Where a chat is: in Chat, or behind a quick button, which asks only for a conversation no chat in Chat is on. */
export type Place = "chat" | "quick";

export class ChatTab {
  private readonly chats = new Map<ChatController, Place>();

  join(chat: ChatController, place: Place): void {
    this.chats.set(chat, place);
  }

  leave(chat: ChatController): void {
    this.chats.delete(chat);
  }

  all(): ChatController[] {
    return [...this.chats.keys()];
  }

  /** Whether `chat` asks what the run in `threadId` waits on: no other chat runs its own reply there (that one asks
   * as part of it), and `chat` is in Chat or no chat in Chat is on the conversation. */
  asks(chat: ChatController, threadId: string): boolean {
    const there = this.all().filter((other) => other !== chat && other.getSnapshot().threadId === threadId);
    if (there.some((other) => other.getSnapshot().busy)) return false;
    return this.chats.get(chat) === "chat" || !there.some((other) => this.chats.get(other) === "chat");
  }
}
