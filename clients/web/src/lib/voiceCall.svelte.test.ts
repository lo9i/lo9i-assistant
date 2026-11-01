import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "./api/errors";
import { VoiceCall, type CallClient } from "./voiceCall.svelte";

// The browser's WebRTC as a call uses it: no audio, the offer and answer and the events' channel.
class FakeChannel {
  onmessage: ((e: { data: string }) => void) | null = null;
  constructor(readonly label: string) {}
}

class FakePeer {
  static last: FakePeer;
  tracks: unknown[] = [];
  channels: FakeChannel[] = [];
  remote: RTCSessionDescriptionInit | null = null;
  closed = false;
  connectionState = "new";
  ontrack: unknown = null;
  onconnectionstatechange: (() => void) | null = null;
  constructor() {
    FakePeer.last = this;
  }
  addTrack(track: unknown) {
    this.tracks.push(track);
  }
  createDataChannel(label: string) {
    const channel = new FakeChannel(label);
    this.channels.push(channel);
    return channel;
  }
  async createOffer() {
    return { type: "offer", sdp: "v=0 offer" };
  }
  async setLocalDescription() {}
  async setRemoteDescription(answer: RTCSessionDescriptionInit) {
    this.remote = answer;
  }
  close() {
    this.closed = true;
  }
}

const track = {
  enabled: true,
  stopped: false,
  stop() {
    this.stopped = true;
  },
};

function client(start: CallClient["start"] = async () => ({ call_id: "rtc_1", sdp: "v=0 answer" })) {
  return { start: vi.fn(start), end: vi.fn(async () => true) };
}

beforeEach(() => {
  track.enabled = true;
  track.stopped = false;
  vi.stubGlobal("RTCPeerConnection", FakePeer);
  vi.stubGlobal(
    "Audio",
    class {
      autoplay = false;
      srcObject: unknown = null;
      play = async () => {};
    },
  );
  vi.stubGlobal("navigator", { mediaDevices: { getUserMedia: async () => ({ getAudioTracks: () => [track], getTracks: () => [track] }) } });
});

afterEach(() => vi.unstubAllGlobals());

describe("a voice call", () => {
  it("sends the offer to the daemon, completes the connection with OpenAI's answer, and shows the call's events", async () => {
    const call = new VoiceCall();
    const daemon = client();
    await call.start(daemon, "t1");
    expect(daemon.start).toHaveBeenCalledWith("t1", "v=0 offer");
    expect(FakePeer.last.remote).toEqual({ type: "answer", sdp: "v=0 answer" });
    expect(FakePeer.last.tracks).toEqual([track]);
    expect([call.state, call.threadId]).toEqual(["live", "t1"]);
    // OpenAI's events come on the "oai-events" channel.
    const events = FakePeer.last.channels.find((c) => c.label === "oai-events");
    events?.onmessage?.({ data: JSON.stringify({ type: "input_audio_buffer.speech_started" }) });
    expect(call.transcript.listening).toBe(true);
    call.toggleMute();
    expect(track.enabled).toBe(false);
    await call.stop(daemon);
    expect(daemon.end).toHaveBeenCalledWith("rtc_1");
    expect([call.state, FakePeer.last.closed, track.stopped]).toEqual(["idle", true, true]);
  });

  it("says why it couldn't start and lets the microphone go", async () => {
    const call = new VoiceCall();
    await call.start(
      client(async () => {
        throw new ApiError(409, "Live voice calls need an OpenAI API key: add one in Settings → Audio.");
      }),
      "t1",
    );
    expect(call.state).toBe("idle");
    expect(call.error).toContain("OpenAI API key");
    expect(track.stopped).toBe(true);
  });

  it("ends when the daemon says its call ended, and not for another", async () => {
    const call = new VoiceCall();
    await call.start(client(), "t1");
    call.ended("rtc_other");
    expect(call.state).toBe("live");
    call.ended("rtc_1");
    expect(call.state).toBe("idle");
  });

  it("hangs up a call answered after it was hung up while connecting", async () => {
    const call = new VoiceCall();
    let answer: (value: { call_id: string; sdp: string }) => void = () => {};
    const daemon = client(() => new Promise((resolve) => (answer = resolve)));
    const starting = call.start(daemon, "t1");
    await vi.waitFor(() => expect(daemon.start).toHaveBeenCalled());
    await call.stop(daemon);
    answer({ call_id: "rtc_late", sdp: "v=0" });
    await starting;
    expect(daemon.end).toHaveBeenCalledWith("rtc_late");
    expect(call.state).toBe("idle");
  });
});
