// The conversations this browser tab is on, kept across reloads: the chat, and the voice button's
// own. sessionStorage is per tab, so a new tab starts new conversations. Storage can be unavailable
// (private windows, blocked site data); the tab then starts fresh on reload.
const KEYS = { chat: "lo9i.thread", voice: "lo9i.voiceThread" };

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
