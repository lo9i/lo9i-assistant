import { render } from "svelte/server";
import { describe, expect, it, vi } from "vitest";
import ApprovalModal from "./ApprovalModal.svelte";

vi.mock("$lib/daemon.svelte", () => ({ useDaemon: () => ({ client: {} }) }));

describe("ApprovalModal", () => {
  it("shows a plugin the agent offers as its install", () => {
    const skill = {
      name: "notes",
      description: "Keep notes in a folder",
      files: [],
      installed: false,
      version: "",
      installed_version: "",
      category: "other",
    };
    const approval = { type: "ApprovalRequired" as const, interrupt_id: "i1", request: { kind: "plugin", name: "notes", skill } };
    const { body } = render(ApprovalModal, { props: { approval, onanswer: () => {} } });
    expect(body).toContain("Install notes");
    expect(body).not.toContain("Approve");
  });
});
