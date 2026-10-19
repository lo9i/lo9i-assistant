// The conversations this browser tab is on, kept across reloads: the chat's open ones, and the voice
// button's own. sessionStorage is per tab, so a new tab starts new conversations. Storage can be unavailable
// (private windows, blocked site data); the tab then starts fresh on reload.
const KEYS = { chat: "lo9i.thread", voice: "lo9i.voiceThread" };
const OPEN = "lo9i.openThreads";

export type Lane = keyof typeof KEYS;

export function savedThread(lane: Lane = "chat"): string | null {
  try {
    return sessionStorage.getItem(KEYS[lane]);
  } catch {
    return null;
  }
}

export function saveThread(threadId: string, lane: Lane = "chat"): void {
  try {
    sessionStorage.setItem(KEYS[lane], threadId);
  } catch {
    // Not kept; see above.
  }
}

/** The chat's open conversations and which one was shown; before there were several, the one it was on. */
export function savedOpen(): { threads: string[]; active: number } {
  try {
    const saved = JSON.parse(sessionStorage.getItem(OPEN) ?? "null") as { threads: string[]; active: number } | null;
    if (saved && Array.isArray(saved.threads)) return saved;
  } catch {
    // Not kept, or not readable; see above.
  }
  const one = savedThread();
  return { threads: one ? [one] : [], active: 0 };
}

export function saveOpen(open: { threads: string[]; active: number }): void {
  try {
    sessionStorage.setItem(OPEN, JSON.stringify(open));
  } catch {
    // Not kept; see above.
  }
}
