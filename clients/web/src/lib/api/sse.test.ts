import { describe, expect, it } from "vitest";
import { readEventBatches, readEvents } from "./sse";
import { body } from "./testing";

async function all(stream: ReadableStream<Uint8Array>) {
  const events = [];
  for await (const event of readEvents(stream)) events.push(event);
  return events;
}

describe("readEvents", () => {
  it("reads ids, types and multi-line data", async () => {
    const events = await all(body("id: 1\r\ndata: a\r\ndata: b\r\n\r\n", "id: 2\r\nevent: end\r\ndata: {}\r\n\r\n"));
    expect(events).toEqual([
      { id: "1", event: "message", data: "a\nb" },
      { id: "2", event: "end", data: "{}" },
    ]);
  });

  it("keeps a line break split across chunks as one", async () => {
    const events = await all(body("id: 7\r", "\nevent: end\r", "\ndata: {}\r\n\r\n"));
    expect(events).toEqual([{ id: "7", event: "end", data: "{}" }]);
  });

  it("skips comments and events without data", async () => {
    expect(await all(body(": ping\n\nevent: x\n\n"))).toEqual([]);
  });
});

describe("readEventBatches", () => {
  it("gives the events each read completed together", async () => {
    const batches = [];
    for await (const batch of readEventBatches(body("id: 1\ndata: a\n\nid: 2\ndata: b\n\nid: 3\nda", "ta: c\n\n"))) {
      batches.push(batch.map((event) => event.data));
    }
    expect(batches).toEqual([["a", "b"], ["c"]]);
  });
});
