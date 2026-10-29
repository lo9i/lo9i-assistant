import { describe, expect, it } from "vitest";
import type { Conversation } from "../api/types";
import { matching, messageSearch } from "./search";

const conversation = (thread_id: string, title: string): Conversation => ({
  thread_id,
  title,
  started_at: "2026-01-01",
  updated_at: "2026-01-01",
  archived_upto: 0,
  titled: true,
  channels: [],
  tags: [],
  archived: false,
  inbox: false,
});

const growing = conversation("owner:5e6f8f733ae8", "Growing the lo9i-assistant project: launch and new features");
const hackers = conversation("owner:b", "Hackers and painters");
const trip = conversation("owner:c", "Trip to Rome");
const all = [growing, hackers, trip];

describe("matching", () => {
  it("shows every conversation without a search", () => {
    expect(matching(all, "  ", [growing.thread_id])).toEqual(all);
  });

  it("finds a conversation by its title or by what was said in it", () => {
    expect(matching(all, "Hacker", [growing.thread_id])).toEqual([growing, hackers]);
  });

  it("matches titles alone until the daemon answers", () => {
    expect(matching(all, "rome", [])).toEqual([trip]);
  });

  it("leaves what was said out of a one-letter search", () => {
    expect(matching(all, "z", [growing.thread_id])).toEqual([]);
  });
});

describe("messageSearch", () => {
  it("asks the daemon from two letters on", () => {
    expect(messageSearch(" h ")).toBe("");
    expect(messageSearch(" ha ")).toBe("ha");
  });
});
