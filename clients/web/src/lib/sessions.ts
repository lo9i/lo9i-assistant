// How a connected client (a session) is named next to its device and its conversation, on the
// Active sessions, Devices and Conversations pages.
import type { ConnectedClient, Conversation, Device } from "./api/types";
import { t, type Key } from "./i18n.svelte";

const KINDS: Record<string, Key> = { cli: "sessions.terminal", web: "sessions.browserTab" };

export function clientLabel(c: ConnectedClient): string {
  return c.kind in KINDS ? t(KINDS[c.kind]) : c.kind || t("sessions.unknownClient");
}

/** Clients on the Unix socket run on the daemon's host and need no device. */
export function deviceLabel(c: ConnectedClient, devices: Device[] | undefined): string {
  if (!c.device_id) return t("sessions.thisHost");
  return devices?.find((d) => d.id === c.device_id)?.name ?? t("sessions.unknownDevice");
}

export function conversationLabel(c: ConnectedClient, conversations: Conversation[] | undefined): string {
  if (!c.thread_id) return t("sessions.noneYet");
  const conversation = conversations?.find((x) => x.thread_id === c.thread_id);
  return conversation ? conversation.title || t("common.untitled") : t("nav.newConversation");
}
