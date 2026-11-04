// What waits to be read in a conversation, shown in the queue above the message box instead of the chat: the
// messages the agent it's handed to hasn't got to (core/agent_tasks/: edited and removed through the daemon until it
// takes them), then those this page sends once the reply running ends (ChatController's queue).
import type { Queued } from "./controller";
import type { Waiting } from "./transcript";

/** One message in the queue, by a `key` that stays while it waits. `fixed`: the inbox sent it on here, so it can't be
 * changed. `agent` is its id in the agent's inbox; `queued` its id in this page's queue. */
export type QueueEntry = { key: string; text: string; files: string[]; fixed: boolean } & ({ agent: string } | { queued: number });

/** The queue, in the order its messages will be read: what the agent was sent first. */
export function queueEntries(waiting: readonly Waiting[], queued: readonly Queued[]): QueueEntry[] {
  return [
    ...waiting.map((w) => ({ key: `agent:${w.messageId}`, text: w.text, files: w.files, fixed: false, agent: w.messageId })),
    ...queued.map((q) => ({
      key: `here:${q.id}`,
      text: q.text,
      files: q.files.map((f) => f.name),
      fixed: q.dispatched !== undefined,
      queued: q.id,
    })),
  ];
}
