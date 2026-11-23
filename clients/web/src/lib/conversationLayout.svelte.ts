// How Chat's page lays out the conversations (lib/chat/cardLayout.ts), kept per browser: the same next time, in any
// tab. Storage can be unavailable; the layout is then kept while the page stays open.
import { parsed, restored, serialized, type Layout } from "./chat/cardLayout";

const KEY = "lo9i.conversationLayout";

class ConversationLayout {
  current = $state.raw<Layout>(read());
  // The latest layout, outside reactivity: a teardown reads `current` as it was before the change that tears it down.
  #latest = this.current;

  change(next: Layout): void {
    this.current = next;
    this.#latest = next;
    try {
      localStorage.setItem(KEY, serialized(next));
    } catch {
      // Kept for this page only.
    }
  }

  /** Full screen given back, the rest as it is now; safe in a teardown, where `current` may be the layout before the
   * change that ends it (List pressed, the cards view going). */
  restore(): void {
    if (this.#latest.maximized !== null) this.change(restored(this.#latest));
  }
}

function read(): Layout {
  try {
    return parsed(localStorage.getItem(KEY));
  } catch {
    return parsed(null);
  }
}

export const conversationLayout = new ConversationLayout();
