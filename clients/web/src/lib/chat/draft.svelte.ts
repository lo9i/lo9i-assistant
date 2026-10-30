// The message being typed in the chat, one per conversation: each conversation's box shows its own text and files,
// and coming back finds them again; a conversation side by side and its card share one. Kept while the user visits
// another page (the chat panel is unmounted then). The text is also kept across reloads, per tab like the
// conversation (tabThread.ts); attached files only while the page stays open. Storage can be unavailable; the text
// is then kept only while the page stays open.
const KEY = "lo9i.draft";

/** One conversation's unsent text and files, bound to its message box. */
export type DraftBox = { text: string; files: File[] };

class Draft {
  #texts = $state<Record<string, string>>(read());
  #files = $state<Record<string, File[]>>({});

  /** The box of the conversation `thread`. */
  of(thread: string): DraftBox {
    // The getters' own `this` is the box.
    const draft = this;
    return {
      get text() {
        return draft.#texts[thread] ?? "";
      },
      set text(value) {
        draft.#setText(thread, value);
      },
      get files() {
        return draft.#files[thread] ?? [];
      },
      set files(value) {
        draft.#setFiles(thread, value);
      },
    };
  }

  #setText(thread: string, value: string): void {
    if (value) this.#texts[thread] = value;
    else delete this.#texts[thread];
    try {
      sessionStorage.setItem(KEY, JSON.stringify(this.#texts));
    } catch {
      // Kept for this page only.
    }
  }

  #setFiles(thread: string, value: File[]): void {
    if (value.length) this.#files[thread] = value;
    else delete this.#files[thread];
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
