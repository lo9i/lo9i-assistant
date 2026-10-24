// Tool calls from history show their arguments on one line and the start of their output (transcript.ts,
// `partial`); the whole call loads the first time one is opened. One that failed to load tries again when it's
// opened again.
import type { ShownCall } from "../api/types";
import type { ToolItem } from "./transcript";

export type WholeCall = { state: "loading" } | { state: "failed" } | { state: "loaded"; call: ShownCall };

export class WholeCalls {
  #calls = $state<Record<string, WholeCall>>({});

  get(callId?: string): WholeCall | undefined {
    return callId ? this.#calls[callId] : undefined;
  }

  async open(item: ToolItem, load: (callId: string) => Promise<ShownCall>): Promise<void> {
    const callId = item.callId;
    if (!item.partial || !callId || (this.#calls[callId] && this.#calls[callId].state !== "failed")) return;
    this.#calls[callId] = { state: "loading" };
    try {
      this.#calls[callId] = { state: "loaded", call: await load(callId) };
    } catch {
      this.#calls[callId] = { state: "failed" };
    }
  }
}
