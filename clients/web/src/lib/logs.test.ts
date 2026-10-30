import { describe, expect, it, vi } from "vitest";
import { LogsGroup } from "./api/client";
import { LogStreams } from "./api/logStreams";
import type { Transport } from "./api/transport";
import type { LogEntry, LogPage } from "./api/types";
import { applyLogEvent, fileSize, levelLabel, logLine, tone } from "./logs";

function entry(message: string, level = "INFO"): LogEntry {
  return { time: "2026-10-07 10:00:00,000", level, logger: "assistant.core.mcp.hub", component: "mcp", message };
}

function page(...entries: LogEntry[]): LogPage {
  return { file: { name: "daemon", file_name: "daemon.log", description: "", path: "/x/daemon.log", size: 10 }, entries };
}

describe("applyLogEvent", () => {
  it("replaces everything with a page", () => {
    expect(applyLogEvent([entry("old")], { kind: "page", page: page(entry("new")) }, 100)).toEqual([entry("new")]);
  });

  it("adds a new entry at the bottom and keeps only the latest lines", () => {
    const shown = applyLogEvent([entry("a"), entry("b")], { kind: "entry", entry: entry("c") }, 2);
    expect(shown.map((e) => e.message)).toEqual(["b", "c"]);
  });
});

describe("log lines", () => {
  it("tints warnings amber and errors red", () => {
    expect([tone("INFO"), tone("WARNING"), tone("ERROR"), tone("CRITICAL")]).toEqual(["", "warn", "danger", "danger"]);
  });

  it("reads like the file", () => {
    expect(logLine(entry("ready"))).toBe("2026-10-07 10:00:00,000 INFO assistant.core.mcp.hub: ready");
    expect(logLine({ ...entry("crash before logging"), level: "", time: "", logger: "" })).toBe("crash before logging");
    expect(levelLabel("WARNING")).toBe("Warning");
    expect(fileSize(2048)).toBe("2.0 KB");
  });
});

describe("LogsGroup", () => {
  it("reads a page, and follows down the event stream instead of a stream of its own", async () => {
    const calls: [string, string, unknown][] = [];
    const transport: Transport = {
      clientId: "test",
      request: async <T>(method: string, path: string, sent?: FormData | object) => {
        calls.push([method, path, sent]);
        return page() as T;
      },
      blob: () => Promise.reject(new Error("unused")),
      stream: () => Promise.reject(new Error("a log has no stream of its own")),
    };
    const following = new LogStreams(transport);
    const logs = new LogsGroup(transport, following);
    await logs.page("daemon", { level: "WARNING", component: "", lines: 50 });
    const stop = new AbortController();
    const events = logs.follow("daemon", { level: "", component: "mcp", lines: 100 }, stop.signal);
    const first = events.next();
    await vi.waitFor(() => expect(calls).toHaveLength(2));
    const follow = decodeURIComponent(calls[1][1].split("/").pop()!);
    following.receive("log_page", { follow, page: page(entry("before")) });
    following.receive("log_entry", { follow, entry: entry("after") });
    expect((await first).value).toEqual({ kind: "page", page: page(entry("before")) });
    expect((await events.next()).value).toEqual({ kind: "entry", entry: entry("after") });
    stop.abort();
    await expect(events.next()).rejects.toThrow();
    expect(calls.map(([method, path]) => `${method} ${path}`)).toEqual([
      "GET /logs/daemon?lines=50&level=WARNING",
      `PUT /events/logs/${follow}`,
      `DELETE /events/logs/${follow}`,
    ]);
    expect(calls[1][2]).toEqual({ name: "daemon", lines: 100, component: "mcp" });
  });
});
