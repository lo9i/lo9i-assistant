import { describe, expect, it } from "vitest";
import { LiveConversation, type Conversations } from "./live";

const daemon: Conversations = {
  clientId: "me",
  inboxThread: async () => "inbox",
  newThread: async () => "t2",
  resumeThread: async () => {},
  leaveThread: async () => {},
};

const live = () => new LiveConversation(daemon, { channel: "web", thread_id: "t1" });

describe("LiveConversation", () => {
  it("reports a reply left running once, when it finishes", async () => {
    const conversation = live();
    await conversation.startNew(true);
    expect(conversation.session.thread_id).toBe("t2");
    const finished = { run_id: "r", thread_id: "t1", channel: "web", status: "ok", reply: "hi" };
    expect(conversation.leftRunFinished(finished)).toBe(true);
    expect(conversation.leftRunFinished(finished)).toBe(false);
  });

  it("resumes an earlier conversation", async () => {
    const conversation = live();
    await conversation.resume("t0");
    expect(conversation.session.thread_id).toBe("t0");
  });

  it("tells runs started by this client apart from the rest", () => {
    const conversation = live();
    const run = { run_id: "r", thread_id: "t1", channel: "web", text: "hi" };
    expect(conversation.startedElsewhere({ ...run, client_id: "other-tab" })).toBe(true);
    expect(conversation.startedElsewhere({ ...run, channel: "telegram", client_id: "" })).toBe(true);
    expect(conversation.startedElsewhere({ ...run, client_id: "me" })).toBe(false);
    expect(conversation.startedElsewhere({ ...run, thread_id: "t0", client_id: "other-tab" })).toBe(false);
  });
});
