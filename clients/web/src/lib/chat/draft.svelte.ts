// The message being typed in the chat, one per conversation: switching conversations shows each one's
// own text and files, and coming back finds them again. Kept while the user visits another page (the
// chat panel is unmounted then). The text is also kept across reloads, per tab like the conversation
// (tabThread.ts); attached files only while the page stays open. Storage can be unavailable; the text
// is then kept only while the page stays open. A message written on the Chat list waits here, queued,
// until the chat panel opens and sends it.
const KEY = "lo9i.draft";

export type Queued = { text: string; files: File[] };

class Draft {
  /** The conversation shown; the chat panel sets it. */
  thread = $state("");
  #texts = $state<Record<string, string>>(read());
  #files = $state<Record<string, File[]>>({});
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
    return this.#texts[this.thread] ?? "";
  }

  set text(value: string) {
    if (value) this.#texts[this.thread] = value;
    else delete this.#texts[this.thread];
    try {
      sessionStorage.setItem(KEY, JSON.stringify(this.#texts));
    } catch {
      // Kept for this page only.
    }
  }

  get files(): File[] {
    return this.#files[this.thread] ?? [];
  }

  set files(value: File[]) {
    if (value.length) this.#files[this.thread] = value;
    else delete this.#files[this.thread];
  }
}

function read(): Record<string, string> {
  try {
    const parsed: unknown = JSON.parse(sessionStorage.getItem(KEY) ?? "{}");
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? (parsed as Record<string, string>) : {};
  } catch {
    return {};
  }
}

export const draft = new Draft();
