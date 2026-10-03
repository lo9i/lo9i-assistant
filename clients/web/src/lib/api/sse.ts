/** One Server-Sent Event. */
export type ServerEvent = { id: string; event: string; data: string };

/** Reads a Server-Sent Events body into events, like src/assistant/client/sse.py. */
export async function* readEvents(body: ReadableStream<Uint8Array>): AsyncGenerator<ServerEvent> {
  let id = "";
  let event = "message";
  let data: string[] = [];
  for await (const line of lines(body)) {
    if (line === "") {
      if (data.length) yield { id, event, data: data.join("\n") };
      event = "message";
      data = [];
      continue;
    }
    const [field, value] = splitField(line);
    if (field === "id") id = value;
    else if (field === "event") event = value;
    else if (field === "data") data.push(value);
  }
}

function splitField(line: string): [string, string] {
  const colon = line.indexOf(":");
  if (colon < 0) return [line, ""];
  const value = line.slice(colon + 1);
  return [line.slice(0, colon), value.startsWith(" ") ? value.slice(1) : value];
}

async function* lines(body: ReadableStream<Uint8Array>): AsyncGenerator<string> {
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
      yield* parts;
    }
  } finally {
    reader.releaseLock();
  }
}
