// Spoken replies in the browser: the daemon reads the reply aloud (Settings → Audio) and the page
// plays it. One reply plays at a time.
import type { SpeechStatus } from "./api/types";

/** Whether a reply is spoken, given whether the message it answers was a voice message. */
export function speaksReply(mode: SpeechStatus["spoken_replies"] | undefined, afterVoiceMessage: boolean): boolean {
  return mode === "always" || (mode === "voice" && afterVoiceMessage);
}

export class Player {
  private audio: HTMLAudioElement | null = null;

  /** Plays the audio, stopping whatever was playing. */
  async play(audio: Blob): Promise<void> {
    this.stop();
    const url = URL.createObjectURL(audio);
    const element = new Audio(url);
    element.onended = () => URL.revokeObjectURL(url);
    this.audio = element;
    await element.play();
  }

  stop(): void {
    this.audio?.pause();
    this.audio = null;
  }
}
