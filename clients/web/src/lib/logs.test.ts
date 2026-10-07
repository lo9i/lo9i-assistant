import { describe, expect, it } from "vitest";
import { LogsGroup } from "./api/client";
import { body } from "./api/testing";
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
  it("asks for the picks and follows with a page, then entries", async () => {
    const paths: string[] = [];
    const transport: Transport = {
      clientId: "test",
      request: async <T>(_method: string, path: string) => {
        paths.push(path);
        return page() as T;
      },
      blob: () => Promise.reject(new Error("unused")),
      stream: async (path) => {
        paths.push(path);
        const first = JSON.stringify(page(entry("before")));
        return new Response(body(`event: page\ndata: ${first}\n\n`, `event: entry\ndata: ${JSON.stringify(entry("after"))}\n\n`));
      },
    };
    const logs = new LogsGroup(transport);
    await logs.page("daemon", { level: "WARNING", component: "", lines: 50 });
    const seen = [];
    for await (const event of logs.follow("daemon", { level: "", component: "mcp", lines: 100 }, new AbortController().signal)) {
      seen.push(event);
      if (seen.length === 2) break;
    }
    expect(paths).toEqual(["/logs/daemon?lines=50&level=WARNING", "/logs/daemon/follow?lines=100&component=mcp"]);
    expect(seen).toEqual([
      { kind: "page", page: page(entry("before")) },
      { kind: "entry", entry: entry("after") },
    ]);
  });
});
