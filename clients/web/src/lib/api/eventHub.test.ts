import { describe, expect, it, vi } from "vitest";
import type { DaemonClient } from "./client";
import { EventHub } from "./eventHub";
import type { BusEvent } from "./types";

/** A client whose events stream opens once per entry, with that entry's events, and is lost after each. */
function client(connections: BusEvent[][]): DaemonClient {
  return {
    async *events(_signal: AbortSignal, onOpen?: () => void, onLost?: () => void) {
      for (const events of connections) {
        onOpen?.();
        yield* events;
        onLost?.();
      }
    },
  } as unknown as DaemonClient;
}

describe("EventHub", () => {
  it("tells when the stream opens again, not when it first opens", async () => {
    const hub = new EventHub();
    const seen: string[] = [];
    hub.on(["skills"], () => seen.push("event"));
    hub.onReconnect(() => seen.push("reconnected"));
    await hub.listen(client([[{ kind: "skills", data: {} }], [{ kind: "skills", data: {} }]]), new AbortController().signal);
    expect(seen).toEqual(["event", "reconnected", "event"]);
  });

  it("follows whether the daemon can be reached", async () => {
    const hub = new EventHub();
    const states: string[] = [hub.getConnection()];
    hub.subscribeConnection(() => states.push(hub.getConnection()));
    await hub.listen(client([[], []]), new AbortController().signal);
    expect(states).toEqual(["connecting", "open", "lost", "open", "lost"]);
  });

  it("stops telling once the handler is removed", async () => {
    const hub = new EventHub();
    let reconnects = 0;
    const stop = hub.onReconnect(() => reconnects++);
    stop();
    await hub.listen(client([[], []]), new AbortController().signal);
    expect(reconnects).toBe(0);
  });

  it("reports a handler that fails and keeps dispatching", async () => {
    const report = vi.fn();
    const hub = new EventHub(report);
    const seen: string[] = [];
    hub.on(["agent_finished"], () => {
      throw new Error("Illegal constructor");
    });
    hub.on(["agent_finished"], () => Promise.reject(new Error("later")));
    hub.on(["agent_finished", "skills"], (data) => seen.push(String(data.n)));
    const events: BusEvent[] = [
      { kind: "agent_finished", data: { n: 1 } },
      { kind: "skills", data: { n: 2 } },
    ];
    await hub.listen(client([events]), new AbortController().signal);
    await Promise.resolve();
    expect(seen).toEqual(["1", "2"]);
    expect(report.mock.calls.map(([error]) => (error as Error).message)).toEqual(["Illegal constructor", "later"]);
  });
});
