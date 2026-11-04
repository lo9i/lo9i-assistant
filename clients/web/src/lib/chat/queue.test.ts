import { describe, expect, it } from "vitest";
import { queueEntries } from "./queue";

describe("queueEntries", () => {
  it("lists what the agent was sent first, then what this page queued, a message the inbox sent on as fixed", () => {
    const dispatched = { type: "Dispatched" as const, id: "d1", thread_id: "t1", title: "Trips", text: "flights?", line: "" };
    const entries = queueEntries(
      [{ messageId: "m1", text: "skip the slow tests", files: [] }],
      [
        { id: 3, text: "and the docs", files: [new File(["x"], "notes.txt")] },
        { id: 4, text: "flights?", files: [], dispatched },
      ],
    );
    expect(entries).toEqual([
      { key: "agent:m1", text: "skip the slow tests", files: [], fixed: false, agent: "m1" },
      { key: "here:3", text: "and the docs", files: ["notes.txt"], fixed: false, queued: 3 },
      { key: "here:4", text: "flights?", files: [], fixed: true, queued: 4 },
    ]);
  });
});
