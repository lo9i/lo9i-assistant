// Recording voice messages in the browser. The chosen microphone is a per-browser convenience
// kept in localStorage; recordings are sent as audio attachments, which the daemon transcribes.

const KEY = "lo9i.microphone";
// Opus in WebM where the browser can record it (Chrome, Firefox), else MP4 (Safari).
const TYPES = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4"];

export function preferredMicrophone(): string {
  try {
    return localStorage.getItem(KEY) ?? "";
  } catch {
    return "";
  }
}

export function setPreferredMicrophone(deviceId: string): void {
  try {
    if (deviceId) localStorage.setItem(KEY, deviceId);
    else localStorage.removeItem(KEY);
  } catch {
    // Storage blocked: the browser's default microphone is used.
  }
}

/** Input devices. Names stay empty until the page has been allowed to use the microphone. */
export async function microphones(): Promise<MediaDeviceInfo[]> {
  const devices = await navigator.mediaDevices.enumerateDevices();
  return devices.filter((d) => d.kind === "audioinput");
}

/** The first recording type this browser supports, or "" for its default. */
export function recordingType(supported: (type: string) => boolean): string {
  return TYPES.find(supported) ?? "";
}

/** File name and media type for a recording, without codec parameters. */
export function recordingFile(type: string, at: Date): { name: string; type: string } {
  const base = type.split(";")[0] || "audio/webm";
  const extension = base === "audio/mp4" ? "m4a" : "webm";
  const stamp = at.toISOString().slice(0, 19).replace(/[:T]/g, "-");
  return { name: `voice-${stamp}.${extension}`, type: base };
}

export class Recorder {
  recording = $state(false);
  startedAt = $state(0);
  private recorder: MediaRecorder | null = null;
  private chunks: Blob[] = [];

  /** Asks for the microphone on first use. Throws when the browser or the user refuses. */
  async start(): Promise<void> {
    const deviceId = preferredMicrophone();
    const stream = await navigator.mediaDevices.getUserMedia({ audio: deviceId ? { deviceId: { exact: deviceId } } : true });
    const mimeType = recordingType((t) => MediaRecorder.isTypeSupported(t));
    this.recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
    this.chunks = [];
    this.recorder.ondataavailable = (e) => this.chunks.push(e.data);
    this.recorder.start();
    this.recording = true;
    this.startedAt = Date.now();
  }

  /** Stops and returns the recording as a file. */
  stop(): Promise<File> {
    const recorder = this.recorder;
    if (!recorder) return Promise.reject(new Error("Not recording."));
    return new Promise((done) => {
      recorder.onstop = () => {
        const { name, type } = recordingFile(recorder.mimeType, new Date());
        done(new File(this.chunks, name, { type }));
      };
      this.finish();
    });
  }

  cancel(): void {
    if (this.recorder) this.recorder.onstop = null;
    this.finish();
  }

  private finish(): void {
    this.recorder?.stop();
    this.recorder?.stream.getTracks().forEach((t) => t.stop());
    this.recorder = null;
    this.recording = false;
  }
}
