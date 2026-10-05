import { describe, expect, it } from "vitest";
import type { Conversation } from "../api/types";
import { homeFirst } from "./order";

const conversation = (thread_id: string, updated_at: string, home = false): Conversation => ({
  thread_id,
  title: thread_id,
  started_at: updated_at,
  updated_at,
  archived_upto: 0,
  titled: true,
  home,
});

describe("homeFirst", () => {
  it("puts home first, then the newest", () => {
    const list = [conversation("old", "2026-01-01"), conversation("home", "2025-01-01", true), conversation("new", "2026-02-01")];
    expect(list.sort(homeFirst).map((c) => c.thread_id)).toEqual(["home", "new", "old"]);
  });
});
