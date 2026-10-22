// Reading a daemon event stream that survives dropped connections: after a drop it reconnects and
// resumes after the last event received, so nothing is missed or repeated (like
// src/assistant/client/daemon_client/reconnect.py).
import { ApiError, DaemonUnavailableError, isAbort } from "./errors";
import { readEvents, type ServerEvent } from "./sse";
import type { Transport } from "./transport";

export type ReconnectPolicy = {
  delayMs: number;
  /** Failed attempts in a row before giving up; undefined keeps trying until aborted. */
  attempts?: number;
};

/** Events from the stream at `path` after the event id `after` ("" for the stream's own start),
 * until `signal` aborts. `onOpen` is called each time the stream opens, the first time and after
 * every reconnection, and `onLost` each time it can't be opened or ends, before waiting to try again.
 * Throws DaemonUnavailableError when the policy gives up, and ApiError for a client error (4xx),
 * which reconnecting can't fix. */
export async function* resumableEvents(
  transport: Transport,
  path: string,
  policy: ReconnectPolicy,
  signal: AbortSignal,
  after = "0",
  onOpen: () => void = () => {},
  onLost: () => void = () => {},
): AsyncGenerator<ServerEvent> {
  let lastId = after;
  let failures = 0;
  for (;;) {
    try {
      for await (const event of open(transport, path, lastId, signal, onOpen)) {
        lastId = event.id || lastId;
        failures = 0;
        yield event;
      }
    } catch (error) {
      if (!droppedConnection(error)) throw error;
    }
    onLost();
    failures += 1;
    await waitOrGiveUp(policy, failures, signal);
  }
}

async function* open(transport: Transport, path: string, lastId: string, signal: AbortSignal, onOpen: () => void) {
  const response = await transport.stream(path, lastId, signal);
  if (response.status >= 400 && response.status < 500) {
    throw new ApiError(response.status, response.statusText);
  }
  if (!response.ok || response.body === null) return;
  onOpen();
  yield* readEvents(response.body);
}

/** A connection that failed or broke off, as opposed to an abort or an error reconnecting can't fix. */
function droppedConnection(error: unknown): boolean {
  if (isAbort(error) || error instanceof ApiError) return false;
  return error instanceof DaemonUnavailableError || error instanceof TypeError;
}

async function waitOrGiveUp(policy: ReconnectPolicy, failures: number, signal: AbortSignal): Promise<void> {
  if (policy.attempts !== undefined && failures >= policy.attempts) {
    throw new DaemonUnavailableError("Lost the connection to the daemon.");
  }
  await delay(policy.delayMs, signal);
}

function delay(ms: number, signal: AbortSignal): Promise<void> {
  signal.throwIfAborted();
  return new Promise((resolve, reject) => {
    const timer = setTimeout(resolve, ms);
    signal.addEventListener(
      "abort",
      () => {
        clearTimeout(timer);
        reject(signal.reason);
      },
      { once: true },
    );
  });
}
