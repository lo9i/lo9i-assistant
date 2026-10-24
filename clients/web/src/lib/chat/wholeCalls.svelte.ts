// Tool calls from history show their arguments on one line and the start of their output (transcript.ts,
// `partial`); the whole call loads the first time one is opened, and a step inside one (a delegate call's, a
// handed-off agent's) the first time that's opened. One that failed to load tries again when it's opened again.
import type { ShownCall } from "../api/types";
import type { ToolItem, ToolStep } from "./transcript";

export type WholeCall = { state: "loading" } | { state: "failed" } | { state: "loaded"; call: ShownCall };

export class WholeCalls {
  #calls = $state<Record<string, WholeCall>>({});

  get(callId?: string): WholeCall | undefined {
    return callId ? this.#calls[callId] : undefined;
  }

  getStep(callId: string | undefined, index: number): WholeCall | undefined {
    return callId ? this.#calls[stepKey(callId, index)] : undefined;
  }

  async open(item: ToolItem, load: (callId: string) => Promise<ShownCall>): Promise<void> {
    const callId = item.callId;
    if (item.partial && callId) await this.#load(callId, () => load(callId));
  }

  async openStep(
    item: ToolItem,
    index: number,
    step: ToolStep,
    load: (callId: string, index: number) => Promise<ShownCall>,
  ): Promise<void> {
    const callId = item.callId;
    if (step.partial && callId) await this.#load(stepKey(callId, index), () => load(callId, index));
  }

  async #load(key: string, load: () => Promise<ShownCall>): Promise<void> {
    if (this.#calls[key] && this.#calls[key].state !== "failed") return;
    this.#calls[key] = { state: "loading" };
    try {
      this.#calls[key] = { state: "loaded", call: await load() };
    } catch {
      this.#calls[key] = { state: "failed" };
    }
  }
}

function stepKey(callId: string, index: number): string {
  return `${callId}#${index}`;
}
