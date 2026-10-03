import { goto } from "$app/navigation";
import { resolve } from "$app/paths";
import type { ChatController } from "./controller";
import { GET_TO_KNOW_ME } from "./commands";

/** Starts the get-to-know-you skill in a conversation of its own, and opens it. */
export async function startGetToKnowYou(chat: ChatController): Promise<void> {
  await chat.startNew();
  void chat.send(GET_TO_KNOW_ME, []);
  await goto(resolve("/conversations/open"));
}
