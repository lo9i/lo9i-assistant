import { render } from "svelte/server";
import { describe, expect, it, vi } from "vitest";
import type { TaskSession } from "$lib/api/types";
import TasksPanel from "./TasksPanel.svelte";

vi.mock("$lib/daemon.svelte", () => ({ useDaemon: () => ({ client: {}, hub: {}, notices: {} }) }));

function session(id: string, status: TaskSession["status"], title: string): TaskSession {
  const started_at = new Date(Date.now() - 3 * 60_000).toISOString();
  return {
    id,
    agent: "claude-code",
    name: "Claude Code",
    title,
    repository: "/Users/me/src/app",
    status,
    started_at,
    step: "",
    waiting: 0,
  };
}

const sessions = [session("a", "done", "Fix the tests"), session("b", "running", "Write the docs")];

describe("TasksPanel", () => {
  it("shows a tab per session, the newest picked, with its status, folder and a box to write to its agent", () => {
    const { body } = render(TasksPanel, { props: { threadId: "t", sessions, open: true, ontoggle: () => {} } });
    expect(body).toContain('aria-label="Coding agents"');
    expect(body).toMatch(/class="tab[^"]*"[^>]*aria-selected="false"[^>]*title="Claude Code · Fix the tests"/);
    expect(body).toMatch(/class="tab [^"]*active"[^>]*aria-selected="true"[^>]*title="Claude Code · Write the docs"/);
    expect(body).toContain("working…");
    expect(body).toContain('title="In /Users/me/src/app"');
    expect(body).toContain("3 min");
    expect(body).toContain('placeholder="Write to Claude Code…"');
    expect(body).toContain("Claude Code reads it after its current step.");
    expect(body).toContain('aria-label="Minimize"');
  });

  it("minimized, is a thin bar saying how they're doing that opens it again", () => {
    const { body } = render(TasksPanel, { props: { threadId: "t", sessions, open: false, ontoggle: () => {} } });
    expect(body).toMatch(/class="rail surface--glass status--running[^"]*"[^>]*aria-label="Show the coding agents' work"/);
    expect(body).toContain("Claude Code · working…");
    expect(body).not.toContain("Write to Claude Code");
    const ended = [session("a", "failed", "Fix the tests")];
    expect(render(TasksPanel, { props: { threadId: "t", sessions: ended, open: false, ontoggle: () => {} } }).body).toContain(
      "Claude Code · failed",
    );
  });
});
