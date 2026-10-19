// The daemon events the chat reacts to, like src/assistant/gateways/cli/tui/live.py.
import type { EventHub } from "../api/eventHub";
import type { RunAnnounced, RunFinished } from "../api/types";
import type { ChatController } from "./controller";

/** The chats a run event goes to: one, or every open one. */
type Chats = { all(): ChatController[] };

/** Shows runs started elsewhere and reports replies left running. Returns what stops it. */
export function followRuns(hub: EventHub, chats: Chats): () => void {
  const stops = [
    hub.on(["run"], (data) => chats.all().forEach((chat) => chat.mirror(data as RunAnnounced))),
    hub.on(["run_finished"], (data) => chats.all().forEach((chat) => chat.runFinished(data as RunFinished))),
  ];
  return () => stops.forEach((stop) => stop());
}
