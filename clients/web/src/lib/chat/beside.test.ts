import { describe, expect, it } from "vitest";
import type { Conversation } from "../api/types";
import { besideChoices } from "./beside";

const conversation = (id: string, title: string, updated: string, inbox = false): Conversation =>
  ({ thread_id: id, title, started_at: updated, updated_at: updated, inbox }) as Conversation;

const listed = [
  conversation("inbox", "Inbox", "2026-10-30T12:00", true),
  conversation("a", "Trip to Rome", "2026-10-29T10:00"),
  conversation("b", "Taxes", "2026-10-30T10:00"),
  conversation("c", "Rome hotels", "2026-10-28T10:00"),
];

describe("besideChoices", () => {
  it("offers the other conversations, newest first, never the inbox nor those shown", () => {
    expect(besideChoices(listed, ["b"], "").map((c) => c.thread_id)).toEqual(["a", "c"]);
  });

  it("narrows them to the titles that hold what's typed", () => {
    expect(besideChoices(listed, [], "rome").map((c) => c.thread_id)).toEqual(["a", "c"]);
  });
});
