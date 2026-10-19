import { describe, expect, it } from "vitest";
import type { Conversation } from "../api/types";
import { newestFirst } from "./order";

const conversation = (thread_id: string, updated_at: string): Conversation => ({
  thread_id,
  title: thread_id,
  started_at: updated_at,
  updated_at,
  archived_upto: 0,
  titled: true,
  channels: [],
  tags: [],
  archived: false,
  inbox: false,
});

describe("newestFirst", () => {
  it("puts the newest activity first", () => {
    const list = [conversation("old", "2026-01-01"), conversation("oldest", "2025-01-01"), conversation("new", "2026-02-01")];
    expect(list.sort(newestFirst).map((c) => c.thread_id)).toEqual(["new", "old", "oldest"]);
  });
});
