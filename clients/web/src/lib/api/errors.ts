/** The daemon can't be reached. Clients keep running and report it. */
export class DaemonUnavailableError extends Error {
  name = "DaemonUnavailableError";
}

/** The daemon answered with an error status; `detail` is its message. */
export class ApiError extends Error {
  name = "ApiError";

  constructor(
    readonly status: number,
    readonly detail: string,
  ) {
    super(detail);
  }
}

export function isAbort(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}
