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
};

describe("conversation stats", () => {
  it("sums up the conversation in one line", () => {
    expect(statsLine(stats)).toBe("24 messages · 182k tokens · 37 tools");
    expect(statsLine({ ...stats, messages: 1, tool_calls: 1 })).toBe("1 message · 182k tokens · 1 tool");
  });

  it("has the line's figures alone, for icons", () => {
    expect(statsFigures(stats)).toEqual({ messages: "24", tokens: "182k", tools: "37" });
  });

  it("details every figure in the tooltip, grouped, with the cache's share of the input", () => {
    expect(statsDetail(stats, "UTC")).toEqual([
      {
        title: "Tokens",
        rows: [
          { label: "Input", value: "170,400" },
          { label: "From the cache", value: "120,000", note: "70%" },
          { label: "Output", value: "11,700" },
        ],
      },
      {
        title: "Calls",
        rows: [
          { label: "To the model", value: "30" },
          { label: "To tools", value: "37" },
        ],
      },
      { title: "Time", rows: [{ label: "Started", value: "Fri 23 Oct 08:00" }] },
    ]);
  });

  it("leaves out what a new conversation doesn't have yet", () => {
    const fresh = { ...stats, input_tokens: 0, cache_read_tokens: 0, started_at: null };
    const groups = statsDetail(fresh, "UTC");
    expect(groups.map((g) => g.title)).toEqual(["Tokens", "Calls"]);
    expect(groups[0].rows[1].note).toBeUndefined();
  });

  it("rounds token counts", () => {
    expect([compact(950), compact(4210), compact(182_100), compact(1_340_000)]).toEqual(["950", "4.2k", "182k", "1.3M"]);
  });
});
