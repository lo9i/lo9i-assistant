import { describe, expect, it, vi } from "vitest";
import { ApiError } from "./errors";
import { LogStreams } from "./logStreams";
import type { Transport } from "./transport";
import type { LogEntry, LogEvent, LogPage } from "./types";

function streams(): { logs: LogStreams; request: ReturnType<typeof vi.fn> } {
  const request = vi.fn().mockResolvedValue({ ok: true });
  const transport: Transport = { clientId: "tab", request, blob: vi.fn(), stream: vi.fn() };
  return { logs: new LogStreams(transport), request };
}

function entry(message: string): LogEntry {
  return { time: "2026-10-30 10:00:00,000", level: "INFO", logger: "assistant.core.mcp.hub", component: "mcp", message };
}

function page(...entries: LogEntry[]): LogPage {
  return { file: { name: "daemon", file_name: "daemon.log", description: "", path: "/x/daemon.log", size: 10 }, entries };
}

/** The id the daemon was asked to follow the log under. */
function followId(request: ReturnType<typeof vi.fn>, call = 0): string {
  return decodeURIComponent((request.mock.calls[call][1] as string).split("/").pop()!);
}

async function take(events: AsyncGenerator<LogEvent>, count: number): Promise<LogEvent[]> {
  const got: LogEvent[] = [];
  for await (const event of events) {
    got.push(event);
    if (got.length === count) break;
  }
  return got;
}

describe("LogStreams", () => {
  it("asks for the log and gives its page, then its entries", async () => {
    const { logs, request } = streams();
    const following = take(logs.follow("daemon", { level: "ERROR", component: "", lines: 50 }, new AbortController().signal), 2);
    await vi.waitFor(() => expect(request).toHaveBeenCalled());
    expect(request.mock.calls[0][0]).toBe("PUT");
    expect(request.mock.calls[0][2]).toEqual({ name: "daemon", level: "ERROR", component: "", lines: 50 });
    const follow = followId(request);
    logs.receive("log_page", { follow, page: page(entry("a")) });
    logs.receive("log_entry", { follow, entry: entry("b") });
    expect(await following).toEqual([
      { kind: "page", page: page(entry("a")) },
      { kind: "entry", entry: entry("b") },
    ]);
  });

  it("leaves other kinds of event to the page, and runs to theirs", () => {
    const { logs } = streams();
    expect(logs.receive("memory", {})).toBe(false);
    expect(logs.receive("run_events", {})).toBe(false);
  });

  it("asks again under the same id when the stream opens again, which starts with a new page", async () => {
    const { logs, request } = streams();
    const following = take(logs.follow("daemon", { level: "", component: "", lines: 100 }, new AbortController().signal), 2);
    await vi.waitFor(() => expect(request).toHaveBeenCalledTimes(1));
    const follow = followId(request);
    logs.receive("log_page", { follow, page: page(entry("a")) });
    logs.reopened();
    expect(followId(request, 1)).toBe(follow);
    logs.receive("log_page", { follow, page: page(entry("a"), entry("b")) });
    expect((await following).map((e) => e.kind)).toEqual(["page", "page"]);
  });

  it("fails when the daemon refuses it", async () => {
    const { logs, request } = streams();
    request.mockRejectedValueOnce(new ApiError(400, "Unknown component: nope"));
    const following = take(logs.follow("daemon", { level: "", component: "nope", lines: 100 }, new AbortController().signal), 1);
    await expect(following).rejects.toBeInstanceOf(ApiError);
  });

  it("stops following when aborted, and tells the daemon", async () => {
    const { logs, request } = streams();
    const stop = new AbortController();
    const following = take(logs.follow("daemon", { level: "", component: "", lines: 100 }, stop.signal), 1);
    await vi.waitFor(() => expect(request).toHaveBeenCalledTimes(1));
    stop.abort();
    await expect(following).rejects.toThrow();
    expect(request.mock.calls[1].slice(0, 2)).toEqual(["DELETE", `/events/logs/${followId(request)}`]);
  });
});
