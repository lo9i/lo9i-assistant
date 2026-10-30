// What a conversation's card shows: whether something works in it or waits for the user, and its last messages.
import type { ChatSnapshot } from "./controller";
import { withoutMarkers } from "./choices";
import type { ChatItem } from "./transcript";

export type CardStatus = "waiting" | "working" | "idle";

/** A question or approval waits for the user before anything else; else a reply or task running (`working`, from
 * this tab's chat on it or anywhere, as the daemon lists them). `asking` is what the daemon says the conversation waits
 * on when it isn't open here. */
export function cardStatus(
  open: Pick<ChatSnapshot, "busy" | "mirroring" | "approval"> | null,
  working: boolean,
  asking: boolean,
): CardStatus {
  if (open ? open.approval !== null : asking) return "waiting";
  if (working || (open !== null && (open.busy || open.mirroring))) return "working";
  return "idle";
}

export type Excerpt = { id: number; from: "user" | "assistant" | "agent"; text: string };

/** The last `count` messages with text: the user's, the assistant's (a reply split by tool calls as one) and a task
 * the assistant wrote for its agent. */
export function lastMessages(items: readonly ChatItem[], count: number): Excerpt[] {
  const excerpts: Excerpt[] = [];
  for (const item of items) {
    const excerpt = excerptOf(item);
    if (excerpt === null) continue;
    const last = excerpts.at(-1);
    if (last?.from === "assistant" && excerpt.from === "assistant") last.text = `${last.text}\n\n${excerpt.text}`;
    else excerpts.push(excerpt);
  }
  return excerpts.slice(-count);
}

function excerptOf(item: ChatItem): Excerpt | null {
  if (item.kind === "user") return { id: item.id, from: "user", text: item.text || item.files.join(", ") };
  if (item.kind === "brief") return { id: item.id, from: "agent", text: item.text };
  if (item.kind !== "assistant") return null;
  const text = withoutMarkers(item.text).trim();
  return text ? { id: item.id, from: "assistant", text } : null;
}
