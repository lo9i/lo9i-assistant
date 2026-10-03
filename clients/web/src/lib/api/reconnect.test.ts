import { describe, expect, it } from "vitest";
import { ApiError, DaemonUnavailableError } from "./errors";
import { resumableEvents } from "./reconnect";
import { body } from "./testing";
import type { Transport } from "./transport";

/** Answers each stream request with the next reply, recording the Last-Event-ID it was sent. */
function transport(replies: Array<Response | Error>): Transport & { lastIds: string[] } {
  const lastIds: string[] = [];
  return {
    clientId: "test",
    lastIds,
    request: () => Promise.reject(new Error("unused")),
    blob: () => Promise.reject(new Error("unused")),
    stream: async (_path, lastEventId) => {
      lastIds.push(lastEventId);
      const reply = replies.shift() ?? new DaemonUnavailableError("gone");
      if (reply instanceof Error) throw reply;
      return reply;
    },
  };
}

async function take(events: AsyncGenerator<{ data: string }>, count: number): Promise<string[]> {
  const seen = [];
  for await (const event of events) {
    seen.push(event.data);
    if (seen.length === count) break;
  }
  return seen;
}

describe("resumableEvents", () => {
  it("resumes after the last event when the connection drops", async () => {
    const t = transport([
      new Response(body("id: 1\ndata: a\n\n")),
      new DaemonUnavailableError("restarting"),
      new Response(body("id: 2\ndata: b\n\n")),
    ]);
    const events = resumableEvents(t, "/events", { delayMs: 0 }, new AbortController().signal);
    expect(await take(events, 2)).toEqual(["a", "b"]);
    expect(t.lastIds).toEqual(["0", "1", "1"]);
  });

  it("starts a stream read from now without an id", async () => {
    const t = transport([new Response(body("id: 9\ndata: a\n\n")), new Response(body("id: 10\ndata: b\n\n"))]);
    const events = resumableEvents(t, "/events", { delayMs: 0 }, new AbortController().signal, "");
    expect(await take(events, 2)).toEqual(["a", "b"]);
    expect(t.lastIds).toEqual(["", "9"]);
  });

  it("gives up after the policy's attempts", async () => {
    const t = transport([]);
    const events = resumableEvents(t, "/runs/x/events", { delayMs: 0, attempts: 3 }, new AbortController().signal);
    await expect(take(events, 1)).rejects.toBeInstanceOf(DaemonUnavailableError);
    expect(t.lastIds).toHaveLength(3);
  });

  it("doesn't retry a client error", async () => {
    const t = transport([new Response("", { status: 404 })]);
    const events = resumableEvents(t, "/runs/x/events", { delayMs: 0 }, new AbortController().signal);
    await expect(take(events, 1)).rejects.toBeInstanceOf(ApiError);
  });
});
