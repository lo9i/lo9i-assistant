// How a connected client (a session) is named next to its device and its conversation, on the
// Active sessions, Devices and Conversations pages.
import type { ConnectedClient, Conversation, Device } from "./api/types";

const KINDS: Record<string, string> = { cli: "Terminal", web: "Browser tab" };

export function clientLabel(c: ConnectedClient): string {
  return KINDS[c.kind] ?? (c.kind || "Unknown client");
}

/** Clients on the Unix socket run on the daemon's host and need no device. */
export function deviceLabel(c: ConnectedClient, devices: Device[] | undefined): string {
  if (!c.device_id) return "This host";
  return devices?.find((d) => d.id === c.device_id)?.name ?? "Unknown device";
}

export function conversationLabel(c: ConnectedClient, conversations: Conversation[] | undefined): string {
  if (!c.thread_id) return "None yet";
  const conversation = conversations?.find((x) => x.thread_id === c.thread_id);
  return conversation ? conversation.title || "Untitled" : "New conversation";
}
