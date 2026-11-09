import { render } from "svelte/server";
import { describe, expect, it, vi } from "vitest";
import type { TaskSession } from "$lib/api/types";
import TasksPanel from "./TasksPanel.svelte";

const servers = vi.hoisted(() => ({ data: undefined as unknown }));
vi.mock("$lib/daemon.svelte", () => ({ useDaemon: () => ({ client: {}, hub: {}, notices: {} }), resource: () => servers }));

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
    context_tokens: 0,
    context_limit: 0,
    model: "",
  };
}

const sessions = [session("a", "done", "Fix the tests"), session("b", "running", "Write the docs")];

describe("TasksPanel", () => {
  it("lists a row per session, the newest picked, with its folder, Stop or how it ended, and a box to write to its agent", () => {
    const { body } = render(TasksPanel, { props: { threadId: "t", sessions, open: true, ontoggle: () => {} } });
    expect(body).toContain('aria-label="Coding agents"');
    expect(body).toMatch(/class="pick[^"]*"[^>]*aria-current="false"[^>]*title="Claude Code · Fix the tests"/);
    expect(body).toMatch(/class="pick[^"]*"[^>]*aria-current="true"[^>]*title="Claude Code · Write the docs"/);
    expect(body).toMatch(/<li class="row[^"]*active[^"]*">.*?Write the docs/s);
    expect(body).toContain('aria-label="Close this session"');
    expect(body).toContain('title="done"');
    expect(body).toMatch(/Write the docs.*?<\/span><\/button>\s*<span class="end[^"]*">.*?Stop<\/button>/s);
    expect(body.match(/aria-label="Close this session"/g)).toHaveLength(1);
    expect(body).toContain('title="In /Users/me/src/app"');
    expect(body).toContain(">app</span>");
    expect(body).toContain("3 min");
    expect(body).toContain('placeholder="Write to Claude Code…"');
    expect(body).toContain('aria-label="Minimize"');
  });

  it("minimized, is a thin bar saying how they're doing that opens it again", () => {
    const { body } = render(TasksPanel, { props: { threadId: "t", sessions, open: false, ontoggle: () => {} } });
    expect(body).toMatch(/class="rail surface--glass status--running[^"]*"[^>]*aria-label="Show the coding agents' work"/);
    expect(body).toMatch(/class="rail-label[^"]*">Claude Code<\/span>/);
    expect(body).toMatch(/class="working[^"]*" role="img" title="working…" aria-label="working…"><span class="mark mark--running/);
    expect(body).not.toContain("· working…");
    expect(body).not.toContain("Write to Claude Code");
    const ended = [session("a", "failed", "Fix the tests")];
    expect(render(TasksPanel, { props: { threadId: "t", sessions: ended, open: false, ontoggle: () => {} } }).body).toContain(
      "Claude Code · failed",
    );
  });

  it("draws its accents in the colour of the agent's plugin icon, else in the colour of a conversation handed to one", () => {
    const props = { threadId: "t", sessions, open: true, ontoggle: () => {} };
    expect(render(TasksPanel, { props }).body).toContain("--glow: var(--color-agent)");
    servers.data = [{ name: "claude-code", icon: { name: "", svg: '<svg><path fill="#D97757"/></svg>', mono: false } }];
    const { body } = render(TasksPanel, { props });
    expect(body).toContain("--glow: #d97757");
    expect(body).toContain("--color-accent: #d97757");
    servers.data = undefined;
  });
});
