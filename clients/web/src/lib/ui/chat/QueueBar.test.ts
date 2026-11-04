import { render } from "svelte/server";
import { describe, expect, it } from "vitest";
import type { QueueEntry } from "$lib/chat/queue";
import QueueBar from "./QueueBar.svelte";

const answered = async () => {};
const agent = (text: string, files: string[] = []): QueueEntry => ({ key: `agent:${text}`, text, files, fixed: false, agent: text });

describe("QueueBar", () => {
  it("shows nothing while nothing is queued", () => {
    const { body } = render(QueueBar, { props: { entries: [], onedit: answered, onremove: answered } });
    expect(body).not.toContain("queued");
  });

  it("counts one queued message and shows it to edit or remove, with nothing to fold", () => {
    const { body } = render(QueueBar, { props: { entries: [agent("skip the slow tests")], onedit: answered, onremove: answered } });
    expect(body).toContain("1 queued");
    expect(body).toContain("skip the slow tests");
    expect(body).toContain('aria-label="Edit"');
    expect(body).toContain('aria-label="Remove from the queue"');
    expect(body).not.toContain("aria-expanded");
  });

  it("folds several, and offers neither edit nor remove for one the inbox sent on", () => {
    const sentOn: QueueEntry = { key: "here:1", text: "flights?", files: [], fixed: true, queued: 1 };
    const entries = [agent("see this", ["shot.png"]), sentOn];
    const { body } = render(QueueBar, { props: { entries, onedit: answered, onremove: answered } });
    expect(body).toContain("2 queued");
    expect(body).toContain('aria-expanded="true"');
    expect(body).toContain("1 file");
    expect(body.match(/aria-label="Edit"/g)).toHaveLength(1);
    expect(body).toContain("The inbox sent it on here");
  });
});
