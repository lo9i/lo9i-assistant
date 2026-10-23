// The preference for being told an agent finished (agentDone.ts), and the browser's ways to tell. Kept per
// browser, like the theme; storage can be unavailable.
import type { AgentDonePreference } from "./agentDone";

const KEY = "lo9i.agentDone";
const DEFAULT: AgentDonePreference = { sound: true, popup: true };

class AgentDoneSettings {
  preference = $state<AgentDonePreference>(read());

  set(change: Partial<AgentDonePreference>): void {
    this.preference = { ...this.preference, ...change };
    try {
      localStorage.setItem(KEY, JSON.stringify(this.preference));
    } catch {
      // Kept for this page only.
    }
  }
}

export const agentDone = new AgentDoneSettings();

function read(): AgentDonePreference {
  try {
    const saved = JSON.parse(localStorage.getItem(KEY) ?? "{}");
    return { sound: saved.sound ?? DEFAULT.sound, popup: saved.popup ?? DEFAULT.popup };
  } catch {
    return DEFAULT;
  }
}

let audio: AudioContext | null = null;

/** Two short soft notes, rising: done. */
export function chime(): void {
  try {
    audio ??= new AudioContext();
    void audio.resume();
    const start = audio.currentTime;
    [660, 880].forEach((frequency, i) => note(audio as AudioContext, frequency, start + i * 0.16));
  } catch {
    // No sound on this browser.
  }
}

function note(context: AudioContext, frequency: number, at: number): void {
  const tone = context.createOscillator();
  const volume = context.createGain();
  tone.type = "sine";
  tone.frequency.value = frequency;
  volume.gain.setValueAtTime(0.0001, at);
  volume.gain.exponentialRampToValueAtTime(0.2, at + 0.02);
  volume.gain.exponentialRampToValueAtTime(0.0001, at + 0.3);
  tone.connect(volume).connect(context.destination);
  tone.start(at);
  tone.stop(at + 0.32);
}

/** Whether the browser shows this page's system notifications. */
export function popupsAllowed(): boolean {
  return "Notification" in window && Notification.permission === "granted";
}

/** Asks the browser to show them, the first time; returns whether it does. */
export async function allowPopups(): Promise<boolean> {
  if (!("Notification" in window)) return false;
  if (Notification.permission === "default") await Notification.requestPermission();
  return Notification.permission === "granted";
}

/** A system notification; false when the browser doesn't show them for this page. */
export function systemNotice(title: string, body: string, onclick: () => void): boolean {
  if (!popupsAllowed()) return false;
  const shown = new Notification(title, { body, tag: "lo9i-agent-finished" });
  shown.onclick = () => {
    window.focus();
    onclick();
    shown.close();
  };
  return true;
}
