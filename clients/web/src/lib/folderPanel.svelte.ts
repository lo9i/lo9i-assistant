// Whether the side panel with a folder's files (ui/chat/folder/HandedFolder.svelte) is shown: the handed folder's
// beside a conversation with an agent, the home folder's beside any other. Each conversation has its own, so opening
// it beside one column of the conversation page leaves the others as they are; a conversation shown for the first
// time takes what the panel was last left at, kept per browser (storage can be unavailable). The handed folder's
// starts shown, as it's what the agent works on; the home folder's starts hidden, as it's there in every
// conversation. A narrow screen starts with both hidden, whatever was kept: they cover the chat there.
export const NARROW = "(max-width: 900px)";

class FolderPanel {
  // What a conversation shown for the first time gets: what the panel was last left at.
  #last = $state(false);
  // Each conversation's, from when it was first shown.
  #shown = $state<Record<string, boolean>>({});

  constructor(
    private readonly key: string,
    shownAtFirst: boolean,
  ) {
    this.#last = initial(key, shownAtFirst);
  }

  isOpen(threadId: string): boolean {
    return this.#shown[threadId] ?? this.#last;
  }

  /** The conversation is shown: its panel stays as it is now when another conversation's is opened or closed. */
  keep(threadId: string): void {
    if (!(threadId in this.#shown)) this.#shown[threadId] = this.#last;
  }

  toggle(threadId: string): void {
    this.set(threadId, !this.isOpen(threadId));
  }

  private set(threadId: string, open: boolean): void {
    this.#shown[threadId] = open;
    this.#last = open;
    try {
      localStorage.setItem(this.key, open ? "open" : "closed");
    } catch {
      // Kept for this page only.
    }
  }
}

function initial(key: string, shownAtFirst: boolean): boolean {
  try {
    if (window.matchMedia(NARROW).matches) return false;
    const kept = localStorage.getItem(key);
    return kept === null ? shownAtFirst : kept === "open";
  } catch {
    return shownAtFirst;
  }
}

export const folderPanel = new FolderPanel("lo9i.folderPanel", true);
export const homePanel = new FolderPanel("lo9i.homePanel", false);

// How many conversations' choices a panel keeps: the oldest go first, so storage doesn't grow with every conversation.
const KEPT_CONVERSATIONS = 200;

// A panel of work the assistant sends off: minimized beside every conversation until the user opens it there, as work
// sent off goes on without being watched. What the user leaves it at is kept for that conversation alone, per browser.
class SentOffPanel {
  #open = $state<Record<string, boolean>>({});

  constructor(private readonly key: string) {
    this.#open = keptChoices(key);
  }

  isOpen(threadId: string): boolean {
    return this.#open[threadId] ?? false;
  }

  toggle(threadId: string): void {
    const open = !this.isOpen(threadId);
    delete this.#open[threadId];
    this.#open[threadId] = open;
    const entries = Object.entries(this.#open);
    if (entries.length > KEPT_CONVERSATIONS) this.#open = Object.fromEntries(entries.slice(-KEPT_CONVERSATIONS));
    try {
      localStorage.setItem(this.key, JSON.stringify(this.#open));
    } catch {
      // Kept for this page only.
    }
  }
}

function keptChoices(key: string): Record<string, boolean> {
  try {
    const kept: unknown = JSON.parse(localStorage.getItem(key) ?? "{}");
    if (typeof kept !== "object" || kept === null) return {};
    return Object.fromEntries(Object.entries(kept).filter(([, v]) => typeof v === "boolean"));
  } catch {
    return {};
  }
}

// The side panel of the conversation's background subagents (ui/chat/subagents/): minimized, it's a thin bar with a mark
// for each and how they're doing.
export const subagentsPanel = new SentOffPanel("lo9i.subagentsPanels");
// The side panel of the coding agents' work beside the conversation that started it (ui/chat/tasks/): minimized, it's a
// thin bar saying how they're doing. A new task picks its tab without opening it.
export const tasksPanel = new SentOffPanel("lo9i.tasksPanels");
