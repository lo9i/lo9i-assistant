// A look at a conversation without opening it (a card of Chat's, a row of Home's Conversations card): its messages
// and whether its run waits for the user, loaded when it's shown and again when it changes. One open in this tab
// shows it live instead, from its chat. Call during component setup.
import { DaemonUnavailableError } from "../api/errors";
import type { ShownMessage } from "../api/types";
import { useDaemon } from "../daemon.svelte";
import { describe } from "../notices";

export type Glance = {
  readonly history: ShownMessage[];
  // What the daemon says its run stopped to ask.
  readonly asking: boolean;
  readonly error: string | null;
};

export type Watched = {
  threadId: string;
  /** When it last changed, as the list of conversations says. */
  updatedAt: string;
  /** A reply or task runs in it: its start and end change what it waits on. */
  working: boolean;
  /** Load it: it's in view and not open here. */
  wanted: boolean;
};

export function glance(watched: () => Watched): Glance {
  const { client } = useDaemon();
  let history = $state.raw<ShownMessage[]>([]);
  let asking = $state(false);
  let error = $state<string | null>(null);

  $effect(() => {
    const { threadId, updatedAt, working, wanted } = watched();
    if (!wanted) return;
    void updatedAt;
    void working;
    let current = true;
    Promise.all([client.conversations.messages(threadId), client.conversations.approvals(threadId)]).then(
      ([messages, waiting]) => {
        if (!current) return;
        history = messages;
        asking = waiting.length > 0;
        error = null;
      },
      (e: unknown) => {
        if (current && !(e instanceof DaemonUnavailableError)) error = describe(e);
      },
    );
    return () => {
      current = false;
    };
  });

  return {
    get history() {
      return history;
    },
    get asking() {
      return asking;
    },
    get error() {
      return error;
    },
  };
}
