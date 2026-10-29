// The conversations listed under Chat (lib/chat/openList.ts), live: in the sidebar, and in the switcher Chat's top bar
// shows on a phone, where the sidebar has no room for them. Call during component setup.
import { goto } from "$app/navigation";
import { resolve } from "$app/paths";
import { openList, type OpenItem } from "$lib/chat/openList";
import { TINTS, tints } from "$lib/chat/tints";
import { external, resource, useDaemon } from "$lib/daemon.svelte";
import { openConversation } from "./openConversation";

export type OpenNow = {
  readonly items: OpenItem[];
  // The open ones whose run waits for an answer.
  readonly waiting: number;
  // Each listed conversation's colour while there are colours left (lib/chat/tints.ts).
  tint(threadId: string): string;
  // Shows it: one open here becomes the one shown, another opens beside them.
  show(item: Pick<OpenItem, "key" | "threadId">): Promise<void>;
  close(key: string): void;
};

export const OPEN_PAGE = resolve("/conversations/open");

export function openNow(): OpenNow {
  const { chats, notices } = useDaemon();
  const conversations = resource((c) => c.conversations.list(), ["conversations"]);
  const runs = resource((c) => c.runs.inProgress(), ["run", "run_finished"]);
  const tasks = resource((c) => c.tasks.running(), ["agent_task_progress", "agent_task_reports", "background_ended"]);
  const open = external(chats.subscribe, chats.getSnapshot);
  const items = $derived(
    openList(open.current, conversations.data ?? [], [
      ...(runs.data ?? []).map((r) => r.thread_id),
      ...(tasks.data ?? []).map((t) => t.thread_id),
    ]),
  );
  const tintOf = $derived(tints.for(items.map((e) => e.threadId)));
  return {
    get items() {
      return items;
    },
    get waiting() {
      return open.current.chats.filter((c) => c.state.approval !== null).length;
    },
    tint: (threadId) => tintOf[threadId] ?? TINTS[0],
    async show(item) {
      if (item.key === null) return await openConversation(chats, notices, item.threadId);
      chats.activate(item.key);
      await goto(OPEN_PAGE);
    },
    close: (key) => chats.close(key),
  };
}
