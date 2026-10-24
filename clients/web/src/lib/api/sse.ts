/** One Server-Sent Event. */
export type ServerEvent = { id: string; event: string; data: string };

/** Reads a Server-Sent Events body into events, like src/assistant/client/sse.py. */
export async function* readEvents(body: ReadableStream<Uint8Array>): AsyncGenerator<ServerEvent> {
  for await (const batch of readEventBatches(body)) yield* batch;
}

/** The events each read of the body completed, together, so a reader can apply the ones that came at once in one go:
 * following a run from its start, its past events come in a few large reads. */
export async function* readEventBatches(body: ReadableStream<Uint8Array>): AsyncGenerator<ServerEvent[]> {
  const parser = new EventParser();
  for await (const lines of lineBatches(body)) {
    const events = lines.map((line) => parser.read(line)).filter((event) => event !== null);
    if (events.length) yield events;
  }
}

/** Reads lines one at a time; an empty line ends an event. */
class EventParser {
  private id = "";
  private event = "message";
  private data: string[] = [];

  /** The event the line ends, if it ends one with data. */
  read(line: string): ServerEvent | null {
    if (line === "") return this.end();
    const [field, value] = splitField(line);
    if (field === "id") this.id = value;
    else if (field === "event") this.event = value;
    else if (field === "data") this.data.push(value);
    return null;
  }

  private end(): ServerEvent | null {
    const ended = this.data.length ? { id: this.id, event: this.event, data: this.data.join("\n") } : null;
    this.event = "message";
    this.data = [];
    return ended;
  }
}

function splitField(line: string): [string, string] {
  const colon = line.indexOf(":");
  if (colon < 0) return [line, ""];
  const value = line.slice(colon + 1);
  return [line.slice(0, colon), value.startsWith(" ") ? value.slice(1) : value];
}

/** The whole lines each read of the body completed. */
async function* lineBatches(body: ReadableStream<Uint8Array>): AsyncGenerator<string[]> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) return;
      buffer += decoder.decode(value, { stream: true });
      // A chunk may end between the \r and \n of one line break; keep the \r for the next chunk.
      const cut = buffer.endsWith("\r") ? buffer.length - 1 : buffer.length;
      const parts = buffer.slice(0, cut).split(/\r\n|\r|\n/);
      buffer = (parts.pop() ?? "") + buffer.slice(cut);
      if (parts.length) yield parts;
    }
  } finally {
    reader.releaseLock();
  }
}
