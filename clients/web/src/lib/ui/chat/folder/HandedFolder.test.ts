import { render } from "svelte/server";
import { describe, expect, it, vi } from "vitest";
import type { Handoff } from "$lib/api/types";
import HandedFolder from "./HandedFolder.svelte";

vi.mock("$lib/daemon.svelte", () => ({
  useDaemon: () => ({ client: {}, hub: {} }),
  Resource: class {
    data = { repository: true, truncated: false, changes: [] };
    error = null;
    reload = () => {};
  },
}));

const handoff = { name: "Claude Code", command: "claude", folder: "/Users/me/projects/lo9i" } as Handoff;

describe("HandedFolder", () => {
  it("shows the agent's folder with what changed in it", () => {
    const { body } = render(HandedFolder, { props: { threadId: "t", handoff, onclose: () => {} } });
    expect(body).toContain('title="/Users/me/projects/lo9i">lo9i<');
    expect(body).toContain('aria-label="Changed"');
    expect(body).toContain('title="Hide the agent\'s folder"');
  });

  it("shows the home folder, without changes, beside a conversation not handed to an agent", () => {
    const { body } = render(HandedFolder, { props: { threadId: "t", handoff: null, onclose: () => {} } });
    expect(body).toContain('title="~">Home folder<');
    expect(body).not.toContain('aria-label="Changed"');
    expect(body).toContain('title="Hide your home folder"');
  });
});
