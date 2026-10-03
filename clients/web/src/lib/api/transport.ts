import { ApiError, DaemonUnavailableError, isAbort } from "./errors";

// Every request carries these (see src/assistant/protocol.py).
const CLIENT_HEADER = "X-Lo9i-Client";
const CLIENT_ID_HEADER = "X-Lo9i-Client-Id";
// Joins a client's id and the name of a second conversation it holds, such as the voice button's.
const CLIENT_ID_PART = "/";

/** The id a client uses for a second conversation it holds at the same time as its own. */
export function partClientId(clientId: string, part: string): string {
  return `${clientId}${CLIENT_ID_PART}${part}`;
}

/** The HTTP connection shared by every part of the client. */
export interface Transport {
  /** How the daemon names this client. */
  readonly clientId: string;
  /** The JSON response. Throws ApiError for an error status, DaemonUnavailableError when unreachable. */
  request<T>(method: string, path: string, body?: FormData | object): Promise<T>;
  /** A binary response, such as audio. Throws like `request`. */
  blob(method: string, path: string, body?: FormData | object): Promise<Blob>;
  /** A Server-Sent Events response, resuming after `lastEventId` ("" to start fresh). */
  stream(path: string, lastEventId: string, signal: AbortSignal): Promise<Response>;
}

export class HttpTransport implements Transport {
  private readonly headers: Record<string, string>;

  constructor(readonly clientId: string = crypto.randomUUID()) {
    this.headers = { [CLIENT_HEADER]: "web", [CLIENT_ID_HEADER]: clientId };
  }

  async request<T>(method: string, path: string, body?: FormData | object): Promise<T> {
    const response = await this.fetch(path, { method, ...this.body(body) });
    if (!response.ok) {
      throw new ApiError(response.status, await detail(response));
    }
    return (await response.json()) as T;
  }

  async blob(method: string, path: string, body?: FormData | object): Promise<Blob> {
    const response = await this.fetch(path, { method, ...this.body(body) });
    if (!response.ok) {
      throw new ApiError(response.status, await detail(response));
    }
    return await response.blob();
  }

  stream(path: string, lastEventId: string, signal: AbortSignal): Promise<Response> {
    return this.fetch(path, { headers: lastEventId ? { "Last-Event-ID": lastEventId } : {}, signal });
  }

  private body(body?: FormData | object): RequestInit {
    if (body === undefined || body instanceof FormData) {
      return { body };
    }
    return { body: JSON.stringify(body), headers: { "Content-Type": "application/json" } };
  }

  private async fetch(path: string, init: RequestInit): Promise<Response> {
    try {
      return await fetch(path, { ...init, headers: { ...this.headers, ...init.headers } });
    } catch (error) {
      if (isAbort(error)) throw error;
      throw new DaemonUnavailableError(`Can't reach the daemon: ${String(error)}`);
    }
  }
}

async function detail(response: Response): Promise<string> {
  try {
    return String((await response.json()).detail);
  } catch {
    return response.statusText;
  }
}
