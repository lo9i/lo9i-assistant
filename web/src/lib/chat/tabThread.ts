// The conversation this browser tab is on, kept across reloads. sessionStorage is per tab, so a
// new tab starts a new conversation. Storage can be unavailable (private windows, blocked site
// data); the tab then starts fresh on reload.
const KEY = "lo9i.thread";

export function savedThread(): string | null {
  try {
    return sessionStorage.getItem(KEY);
  } catch {
    return null;
  }
}

export function saveThread(threadId: string): void {
  try {
    sessionStorage.setItem(KEY, threadId);
  } catch {
    // Not kept; see above.
  }
}
