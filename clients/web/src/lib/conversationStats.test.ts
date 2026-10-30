import { describe, expect, it } from "vitest";
import type { ConversationStats } from "./api/types";
import { compact, statsDetail, statsFigures, statsLine } from "./conversationStats";

const stats: ConversationStats = {
  thread_id: "owner:abc",
  messages: 24,
  model_calls: 30,
  input_tokens: 170_400,
  cache_read_tokens: 120_000,
  output_tokens: 11_700,
  tool_calls: 37,
  context_tokens: 0,
  context_limit: 150000,
  context_agent: "",
  started_at: "2026-10-23T08:00:00Z",
  last_activity: "2026-10-23T10:00:00Z",
};

describe("conversation stats", () => {
  it("reads as one short line", () => {
    expect(statsLine(stats, "2026-10-23T12:00:00Z")).toBe("24 messages · 182k tokens · 37 tools · 2 h ago");
    expect(statsLine({ ...stats, messages: 1, tool_calls: 1, last_activity: null }, "2026-10-23T12:00:00Z")).toBe(
      "1 message · 182k tokens · 1 tool",
    );
    expect(statsLine(stats, "2026-10-23T10:00:20Z")).toMatch(/just now$/);
  });

  it("gives the line's figures alone, for icons to stand for their words", () => {
    expect(statsFigures(stats, "2026-10-23T12:00:00Z")).toEqual({ messages: "24", tokens: "182k", tools: "37", ago: "2 h ago" });
    expect(statsFigures({ ...stats, last_activity: null }, "2026-10-23T12:00:00Z").ago).toBe("");
  });

  it("details every figure in the tooltip", () => {
    const detail = statsDetail(stats, "UTC").split("\n");
    expect(detail).toEqual([
      "Input tokens: 170,400",
      "Output tokens: 11,700",
      "Cache read tokens: 120,000",
      "Model calls: 30",
      "Tool calls: 37",
      "Started: Fri 23 Oct 08:00",
      "Last activity: Fri 23 Oct 10:00",
    ]);
  });

  it("rounds token counts", () => {
    expect([compact(950), compact(4210), compact(182_100), compact(1_340_000)]).toEqual(["950", "4.2k", "182k", "1.3M"]);
  });
});
