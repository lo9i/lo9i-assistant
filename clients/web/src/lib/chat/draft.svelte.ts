// The message being typed in the chat, kept while the user visits another page (the chat panel is
// unmounted then). Its text is also kept across reloads, per tab like the conversation (tabThread.ts);
// attached files only while the page stays open. Storage can be unavailable; the text is then kept
// only while the page stays open.
const KEY = "lo9i.draft";

class Draft {
  #text = $state(read());
  files = $state<File[]>([]);

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
