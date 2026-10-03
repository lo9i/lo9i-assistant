// Spoken replies in the browser: the daemon reads the reply aloud (Settings → Audio) and the page
// plays it. Sentence by sentence: the first one plays while the next is synthesized, so speech
// starts after one sentence instead of after the whole reply. One reply plays at a time.
import type { SpeechStatus } from "./api/types";

/** Whether a reply is spoken, given whether the message it answers was a voice message. */
export function speaksReply(mode: SpeechStatus["spoken_replies"] | undefined, afterVoiceMessage: boolean): boolean {
  return mode === "always" || (mode === "voice" && afterVoiceMessage);
}

// Sentences shorter than this go with the next one: each part is a request to the daemon.
const SHORT = 40;
// Like the daemon's limit for one reply (core/speech/speakable.py): the rest is left to read.
const MAX_CHARS = 2000;
const CODE = /```[\s\S]*?```/g;
const SENTENCE_END = /(?<=[.!?…:])\s+|\n+/;

/** The reply in the parts to synthesize, in order. Code blocks aren't read, so a part never
 *  splits one; the daemon turns each part's Markdown into speech. */
export function speechParts(text: string): string[] {
  const sentences = text
    .replace(CODE, " ")
    .split(SENTENCE_END)
    .map((s) => s.trim())
    .filter(Boolean);
  const parts: string[] = [];
  let used = 0;
  for (const sentence of sentences) {
    if (used >= MAX_CHARS) break;
    const last = parts.length - 1;
    if (last >= 0 && parts[last].length < SHORT) parts[last] = `${parts[last]} ${sentence}`;
    else parts.push(sentence);
    used += sentence.length;
  }
  return parts;
}

export class Player {
  private audio: HTMLAudioElement | null = null;
  // Each reply spoken gets the next number; a part of an older one doesn't play.
  private generation = 0;

  /** `onend` runs when a reply finishes playing or is stopped. */
  constructor(private readonly onend: () => void = () => {}) {}

  /** Speaks the reply part by part, stopping whatever was playing. `synthesize` turns a part into
   *  audio; `onstart` runs when the first part starts playing. Rejects if a part can't be synthesized. */
  async speak(text: string, synthesize: (part: string) => Promise<Blob>, onstart: () => void = () => {}): Promise<void> {
    this.stop();
    const mine = ++this.generation;
    const parts = speechParts(text);
    let next = parts.length ? synthesize(parts[0]) : null;
    for (let i = 0; next !== null; i++) {
      const audio = await next;
      next = i + 1 < parts.length ? synthesize(parts[i + 1]) : null;
      if (i === 0) onstart();
      if (mine !== this.generation) return void next?.catch(() => {});
      await this.playPart(audio);
      if (mine !== this.generation) return void next?.catch(() => {});
    }
    this.stop();
  }

  stop(): void {
    this.generation++;
    if (!this.audio) return;
    this.audio.pause();
    this.audio = null;
    this.onend();
  }

  /** Resolves when the part has played, or was stopped. */
  private playPart(audio: Blob): Promise<void> {
    const url = URL.createObjectURL(audio);
    const element = new Audio(url);
    this.audio = element;
    return new Promise<void>((resolve, reject) => {
      element.onended = element.onpause = () => {
        URL.revokeObjectURL(url);
        resolve();
      };
      element.play().catch(reject);
    });
  }
}
