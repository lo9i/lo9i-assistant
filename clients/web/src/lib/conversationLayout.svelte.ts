// How Chat's page lays out the conversations (lib/chat/cardLayout.ts), kept per browser: the same next time, in any
// tab. Storage can be unavailable; the layout is then kept while the page stays open.
import { parsed, serialized, type Layout } from "./chat/cardLayout";

const KEY = "lo9i.conversationLayout";

class ConversationLayout {
  current = $state.raw<Layout>(read());

  change(next: Layout): void {
    this.current = next;
    try {
      localStorage.setItem(KEY, serialized(next));
    } catch {
      // Kept for this page only.
    }
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
