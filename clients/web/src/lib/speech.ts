// Spoken replies in the browser: the daemon reads the reply aloud (Settings → Audio) and the page
// plays it. One reply plays at a time.
import type { SpeechStatus } from "./api/types";

/** Whether a reply is spoken, given whether the message it answers was a voice message. */
export function speaksReply(mode: SpeechStatus["spoken_replies"] | undefined, afterVoiceMessage: boolean): boolean {
  return mode === "always" || (mode === "voice" && afterVoiceMessage);
}

export class Player {
  private audio: HTMLAudioElement | null = null;

  /** `onend` runs when a reply finishes playing or is stopped. */
  constructor(private readonly onend: () => void = () => {}) {}

  /** Plays the audio, stopping whatever was playing. */
  async play(audio: Blob): Promise<void> {
    this.stop();
    const url = URL.createObjectURL(audio);
    const element = new Audio(url);
    element.onended = () => {
      URL.revokeObjectURL(url);
      if (this.audio === element) this.stop();
    };
    this.audio = element;
    await element.play();
  }

  stop(): void {
    if (!this.audio) return;
    this.audio.pause();
    this.audio = null;
    this.onend();
  }
}
