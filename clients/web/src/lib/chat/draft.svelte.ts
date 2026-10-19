// The message being typed in the chat, kept while the user visits another page (the chat panel is
// unmounted then). Its text is also kept across reloads, per tab like the conversation (tabThread.ts);
// attached files only while the page stays open. Storage can be unavailable; the text is then kept
// only while the page stays open. A message written on the Chat list waits here, queued, until the chat
// panel opens and sends it.
const KEY = "lo9i.draft";

export type Queued = { text: string; files: File[] };

class Draft {
  #text = $state(read());
  files = $state<File[]>([]);
  #queued: Queued | null = null;

  /** Leaves a message for the chat panel to send when it opens. */
  queue(text: string, files: File[]): void {
    this.#queued = { text, files };
  }

  /** The message left to send, once. */
  takeQueued(): Queued | null {
    const queued = this.#queued;
    this.#queued = null;
    return queued;
  }

  get text(): string {
    return this.#text;
  }

  set text(value: string) {
    this.#text = value;
    try {
      if (value) sessionStorage.setItem(KEY, value);
      else sessionStorage.removeItem(KEY);
    } catch {
      // Kept for this page only.
    }
  }
}

function read(): string {
  try {
    return sessionStorage.getItem(KEY) ?? "";
  } catch {
    return "";
  }
}

export const draft = new Draft();
