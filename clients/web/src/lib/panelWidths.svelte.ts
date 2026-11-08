// The width the user dragged a side panel beside the chat to (ui/chat/PanelDivider.svelte), as a share of the row the
// chat and its panels are in, so it holds when the window changes size. One per panel and state (the folder's tree and
// a file open in it are dragged apart), kept per browser (storage can be unavailable). Without one, or after a
// double-click on the divider, the panel takes its own width from its CSS.
const KEY = "lo9i.panelWidths";

class PanelWidths {
  #shares = $state<Record<string, number>>(load());
  /** The panel being dragged, while one is: its width follows the pointer without easing. */
  dragging = $state<string | null>(null);

  get(name: string): number | null {
    return this.#shares[name] ?? null;
  }

  /** While dragging: kept once the drag ends (`save`). */
  set(name: string, share: number): void {
    this.#shares[name] = share;
  }

  reset(name: string): void {
    delete this.#shares[name];
    this.save();
  }

  save(): void {
    try {
      localStorage.setItem(KEY, JSON.stringify(this.#shares));
    } catch {
      // Kept for this page only.
    }
  }
}

function load(): Record<string, number> {
  try {
    const kept: unknown = JSON.parse(localStorage.getItem(KEY) ?? "{}");
    if (typeof kept !== "object" || kept === null) return {};
    return Object.fromEntries(Object.entries(kept).filter(([, v]) => typeof v === "number" && v > 0 && v < 1));
  } catch {
    return {};
  }
}

export const panelWidths = new PanelWidths();

/** The style a panel takes from `name`'s share: none without one, so its CSS width holds. */
export function panelWidth(name: string): string | undefined {
  const share = panelWidths.get(name);
  return share === null ? undefined : `${(share * 100).toFixed(2)}%`;
}
