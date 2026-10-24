import { render } from "svelte/server";
import { describe, expect, it, vi } from "vitest";
import AgentFolderModal from "./AgentFolderModal.svelte";

vi.mock("$lib/daemon.svelte", () => ({ useDaemon: () => ({ client: {}, notices: {} }) }));

// What it offers once the daemon has listed the folders, and while browsing, is lib/agentFolders.test.ts.
describe("AgentFolderModal", () => {
  it("asks where the agent should work, with a way out", () => {
    const { body } = render(AgentFolderModal, { props: { agentName: "Claude Code", onpick: () => {} } });
    expect(body).toContain("Where should Claude Code work?");
    expect(body).toContain("The workspace, a folder used before, or browse to one.");
    expect(body).toContain("Cancel");
  });
});
