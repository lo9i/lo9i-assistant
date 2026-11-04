import { describe, expect, it } from "vitest";
import type { Conversation } from "./api/types";
import { homeConversations, RECENT } from "./homeConversations";

function conversation(id: string, updated: string, extra: Partial<Conversation> = {}): Conversation {
  return { thread_id: id, title: id, started_at: updated, updated_at: updated, ...extra } as Conversation;
}

const listed = [
  conversation("inbox", "2026-10-30T10:00", { inbox: true }),
  conversation("a", "2026-10-29T10:00"),
  conversation("b", "2026-10-30T09:00"),
  conversation("old", "2026-10-30T08:00", { archived: true }),
];

describe("Home's conversations", () => {
  it("are the most recent ones, newest first, without the inbox or the archived", () => {
    expect(homeConversations(listed).map((c) => c.thread_id)).toEqual(["b", "a"]);
  });

  it(`stop at ${RECENT}`, () => {
    const many = Array.from({ length: RECENT + 3 }, (_, i) => conversation(`t${i}`, `2026-10-${10 + i}T10:00`));
    expect(homeConversations(many)).toHaveLength(RECENT);
    expect(homeConversations(many)[0].thread_id).toBe(`t${RECENT + 2}`);
  });

  it("are none when there are no conversations", () => {
    expect(homeConversations([])).toEqual([]);
  });
});
