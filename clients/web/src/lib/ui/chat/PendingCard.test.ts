import { render } from "svelte/server";
import { describe, expect, it } from "vitest";
import PendingCard from "./PendingCard.svelte";

describe("PendingCard", () => {
  it("says the run waits for an answer, what it asks, and opens it again", () => {
    const approval = { type: "ApprovalRequired" as const, interrupt_id: "i1", request: { kind: "question", question: "Which account?" } };
    const { body } = render(PendingCard, { props: { approval, onopen: () => {} } });
    expect(body).toContain("Waiting for your answer");
    expect(body).toContain("Which account?");
    expect(body).toMatch(/<button[^>]*>Answer<\/button>/);
    expect(body).not.toContain("floating");
  });
});
