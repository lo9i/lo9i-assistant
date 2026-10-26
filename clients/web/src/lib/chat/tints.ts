// The colour of each conversation the sidebar lists. No two listed ones share a colour until every colour is in
// use; then the least used one is shared. A conversation keeps its colour while it's listed, and gets it back when
// it's listed again if no other listed one took it. Kept per browser; storage can be unavailable.
export const TINTS = ["var(--color-accent)", "#e5b931", "#3f9fe0", "#e0603f", "#a56ee0", "#2fc4b2", "#e08a2f", "#e05f9e"];

const KEY = "lo9i.conversation-tints";
// Conversations remembered, the most recently listed last; older ones are forgotten.
const REMEMBERED = 100;

/** The colour index of each of `ids` (listed in this order), given the ones they had (`kept`). */
export function assignTints(ids: string[], kept: Record<string, number>, count = TINTS.length): Record<string, number> {
  const out: Record<string, number> = {};
  const used = new Array<number>(count).fill(0);
  // Their own colour first, for those whose colour no listed one before them has.
  for (const id of ids) {
    const mine = kept[id];
    if (mine !== undefined && mine >= 0 && mine < count && used[mine] === 0) {
      out[id] = mine;
      used[mine]++;
    }
  }
  // The others: a colour nobody listed has, or the least used once all are; their own when it's among those.
  for (const id of ids) {
    if (id in out) continue;
    const least = Math.min(...used);
    const mine = kept[id];
    const pick = mine !== undefined && used[mine] === least ? mine : used.indexOf(least);
    out[id] = pick;
    used[pick]++;
  }
  return out;
}

class Tints {
  private kept: Record<string, number> = read();

  /** The colour of each listed conversation, by thread id. */
  for(ids: string[]): Record<string, string> {
    const picked = assignTints(ids, this.kept);
    if (ids.some((id) => this.kept[id] !== picked[id])) this.remember(ids, picked);
    return Object.fromEntries(ids.map((id) => [id, TINTS[picked[id]]]));
  }

  private remember(ids: string[], picked: Record<string, number>): void {
    const kept = Object.entries(this.kept).filter(([id]) => !(id in picked));
    this.kept = Object.fromEntries([...kept, ...ids.map((id) => [id, picked[id]] as const)].slice(-REMEMBERED));
    try {
      localStorage.setItem(KEY, JSON.stringify(this.kept));
    } catch {
      // Kept for this page only.
    }
  }
}

function read(): Record<string, number> {
  try {
    const saved: unknown = JSON.parse(localStorage.getItem(KEY) ?? "{}");
    return saved && typeof saved === "object" ? (saved as Record<string, number>) : {};
  } catch {
    return {};
  }
}

export const tints = new Tints();
