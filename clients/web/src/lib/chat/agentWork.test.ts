import { describe, expect, it, vi } from "vitest";
import { ApiError } from "../api/errors";
import type { RunningTask } from "../api/types";
import { putBack, tellAgent, workingIn } from "./agentWork";

describe("tellAgent", () => {
  it("passes the message on and says nothing when the agent takes it", async () => {
    const notices = { notify: vi.fn() };
    const call = vi.fn().mockResolvedValue(undefined);
    expect(await tellAgent(call, notices)).toBe(true);
    expect(call).toHaveBeenCalledOnce();
    expect(notices.notify).not.toHaveBeenCalled();
  });

  it("says why as a warning, in the daemon's words, when the agent can't take it", async () => {
    const notices = { notify: vi.fn() };
    const refused = new ApiError(409, "Claude Code isn't working on anything now. Send it as a new message.");
    expect(await tellAgent(() => Promise.reject(refused), notices)).toBe(false);
    expect(notices.notify).toHaveBeenCalledWith("Claude Code isn't working on anything now. Send it as a new message.", "warning");
  });
});

describe("putBack", () => {
  const shot = new File(["png"], "shot.png", { type: "image/png" });
  const log = new File(["log"], "log.txt", { type: "text/plain" });

  it("puts the text and files the agent couldn't take back in an empty box", () => {
    const box = { text: "", files: [] as File[] };
    putBack(box, "see this", [shot]);
    expect(box).toEqual({ text: "see this", files: [shot] });
  });

  it("keeps what was typed meanwhile, and the files attached since after the ones put back", () => {
    const box = { text: "something new", files: [log] };
    putBack(box, "see this", [shot]);
    expect(box).toEqual({ text: "something new", files: [shot, log] });
  });
});

describe("workingIn", () => {
  const task = (id: string, agent: string, thread_id = "t1"): RunningTask => ({
    id,
    agent,
    thread_id,
    asked: "",
    started_at: "2026-10-30T10:00:00Z",
    steps: [],
  });
  const tasks = [task("a", "Claude Code"), task("b", "Copilot"), task("c", "Claude Code", "t2")];

  it("sets apart the task of the agent the conversation is handed to", () => {
    const { handed, others } = workingIn(tasks, "t1", "Claude Code");
    expect(handed?.id).toBe("a");
    expect(others.map((t) => t.id)).toEqual(["b"]);
  });

  it("lists every task in the conversation when it isn't handed over, or its agent isn't working", () => {
    expect(workingIn(tasks, "t1", null)).toEqual({ handed: null, others: [tasks[0], tasks[1]] });
    expect(workingIn(tasks, "t2", "Copilot")).toEqual({ handed: null, others: [tasks[2]] });
  });
});
