// What a run waits for that the user hid (Esc, the scrim or ×) instead of answering: hiding answers nothing, the run
// goes on waiting, and the conversation shows a card that opens it again (ui/chat/PendingAsk.svelte). Only the
// dialog's own buttons answer. Kept by the id of what it waits for, per tab like the conversations open in it
// (tabThread.ts), so a reload or a duplicated tab, which asks the daemon again what the run waits for, keeps it
// hidden. Storage can be unavailable; it's then kept only while the page stays open.
import { SvelteSet } from "svelte/reactivity";

const KEY = "lo9i.hiddenAsks";
// Answered ones are forgotten as they're answered here; this bounds those answered elsewhere.
const KEPT = 50;

class HiddenAsks {
  #ids = new SvelteSet<string>(read());

  has(interruptId: string): boolean {
    return this.#ids.has(interruptId);
  }

  hide(interruptId: string): void {
    this.#ids.add(interruptId);
    this.#save();
  }

  /** Shows it again: opened from its card, or answered. */
  show(interruptId: string): void {
    if (this.#ids.delete(interruptId)) this.#save();
  }

  #save(): void {
    try {
      sessionStorage.setItem(KEY, JSON.stringify([...this.#ids].slice(-KEPT)));
    } catch {
      // Kept for this page only.
    }
  }
}

function read(): string[] {
  try {
    const parsed: unknown = JSON.parse(sessionStorage.getItem(KEY) ?? "[]");
    return Array.isArray(parsed) ? parsed.filter((id): id is string => typeof id === "string") : [];
  } catch {
    return [];
  }
}

export const hiddenAsks = new HiddenAsks();
