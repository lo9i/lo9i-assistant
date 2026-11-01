// A live voice call from this tab (core/voice/), one at a time: the microphone and the voice go straight between the
// browser and OpenAI over WebRTC; the daemon passes the offer on and the answer back (`VoiceCallsGroup.start`) and
// keeps its own connection on the call, through which the assistant answers the voice and what's said is kept in the
// conversation. The call's events come on a data channel too, which the page shows as the latest lines (voiceCall.ts).
import type { VoiceCallAnswer } from "./api/types";
import { preferredMicrophone } from "./microphone.svelte";
import { describe } from "./notices";
import { heard, noLines, type CallTranscript } from "./voiceCall";

/** The daemon's calls a call makes (`client.voiceCalls`). */
export type CallClient = {
  start(threadId: string, sdp: string): Promise<VoiceCallAnswer>;
  end(callId: string): Promise<boolean>;
};

export type CallState = "idle" | "connecting" | "live";

// The data channel's label OpenAI's events come on.
const EVENTS = "oai-events";

export class VoiceCall {
  state = $state<CallState>("idle");
  // The conversation the call is in.
  threadId = $state<string | null>(null);
  transcript = $state<CallTranscript>(noLines);
  muted = $state(false);
  error = $state("");
  private callId = "";
  private peer: RTCPeerConnection | null = null;
  private microphone: MediaStream | null = null;
  private speaker: HTMLAudioElement | null = null;

  /** Whether this browser can make calls here: WebRTC and the microphone need HTTPS or localhost. */
  static supported(): boolean {
    return typeof RTCPeerConnection !== "undefined" && !!globalThis.navigator?.mediaDevices?.getUserMedia;
  }

  /** Starts a call in the conversation, ending the one on in another. Its error, if it fails, is in `error`. */
  async start(client: CallClient, threadId: string): Promise<void> {
    if (this.state !== "idle") await this.stop(client);
    this.state = "connecting";
    this.threadId = threadId;
    this.transcript = noLines;
    this.muted = false;
    this.error = "";
    try {
      const peer = await this.connect();
      const offer = await peer.createOffer();
      await peer.setLocalDescription(offer);
      const answer = await client.start(threadId, offer.sdp ?? "");
      // Hung up while it was being set up.
      if (this.peer !== peer) return void client.end(answer.call_id).catch(() => {});
      this.callId = answer.call_id;
      await peer.setRemoteDescription({ type: "answer", sdp: answer.sdp });
      this.state = "live";
    } catch (error) {
      this.error = describe(error);
      this.release();
    }
  }

  /** Hangs up. */
  async stop(client: CallClient): Promise<void> {
    const callId = this.callId;
    this.release();
    if (callId) await client.end(callId).catch(() => {});
  }

  /** The daemon says a call ended: OpenAI ended it (its hour is up, the connection dropped). */
  ended(callId: string): void {
    if (callId && callId === this.callId) this.release();
  }

  toggleMute(): void {
    this.muted = !this.muted;
    this.microphone?.getAudioTracks().forEach((track) => (track.enabled = !this.muted));
  }

  /** The peer connection with the microphone's track, the voice's playing, and the events' channel, created before
   * the offer so it's part of it. */
  private async connect(): Promise<RTCPeerConnection> {
    const peer = new RTCPeerConnection();
    this.peer = peer;
    const speaker = new Audio();
    speaker.autoplay = true;
    this.speaker = speaker;
    peer.ontrack = (e) => {
      speaker.srcObject = e.streams[0] ?? new MediaStream([e.track]);
      void speaker.play().catch(() => {});
    };
    peer.onconnectionstatechange = () => {
      if (this.peer === peer && ["failed", "closed"].includes(peer.connectionState)) this.release();
    };
    const deviceId = preferredMicrophone();
    const microphone = await navigator.mediaDevices.getUserMedia({ audio: deviceId ? { deviceId: { exact: deviceId } } : true });
    this.microphone = microphone;
    microphone.getAudioTracks().forEach((track) => peer.addTrack(track, microphone));
    const events = peer.createDataChannel(EVENTS);
    events.onmessage = ({ data }) => {
      if (this.peer === peer) this.transcript = heard(this.transcript, JSON.parse(String(data)));
    };
    return peer;
  }

  private release(): void {
    this.microphone?.getTracks().forEach((track) => track.stop());
    this.peer?.close();
    if (this.speaker) this.speaker.srcObject = null;
    this.microphone = this.peer = this.speaker = null;
    this.callId = "";
    this.state = "idle";
  }
}

/** This tab's call. */
export const voiceCall = new VoiceCall();
