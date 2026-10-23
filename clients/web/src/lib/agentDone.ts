// Telling the user that the agent a conversation is handed to (/claude) is done with the job they gave it: once,
// when it has nothing left to do and waits for them, not at each step (an `agent_finished` bus event,
// core/agent/handoffs.py). A sound and a pop-up, each turned on or off in Settings, per browser.
import type { AgentFinished } from "./api/types";
import type { NoticeAction } from "./notices";

export type AgentDonePreference = { sound: boolean; popup: boolean };

/** What telling the user takes; the page's own in the app (AppShell), fakes in the tests. */
export type Telling = {
  chime(): void;
  /** The page is in front of the user: its own notice shows, not the system's. */
  visible(): boolean;
  /** A system notification, when the browser allows them; false when it doesn't. */
  system(title: string, body: string, onclick: () => void): boolean;
  toast(text: string, level: "info" | "warning", action: NoticeAction): void;
};

export function finishedNotice(event: AgentFinished): { title: string; body: string } {
  const title = event.ok ? `${event.agent} finished` : `${event.agent} stopped with a problem`;
  return { title, body: event.text };
}

/** Tells the user as the preference says; `open` opens the conversation. */
export function announce(event: AgentFinished, preference: AgentDonePreference, telling: Telling, open: () => void): void {
  if (preference.sound) telling.chime();
  if (!preference.popup) return;
  const { title, body } = finishedNotice(event);
  if (!telling.visible() && telling.system(title, body, open)) return;
  telling.toast(body ? `${title}: ${body}` : title, event.ok ? "info" : "warning", { label: "Open its conversation", run: open });
}
