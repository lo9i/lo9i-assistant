import { render } from "svelte/server";
import { describe, expect, it, vi } from "vitest";
import type { FoundServer } from "$lib/api/types";
import ApprovalModal from "./ApprovalModal.svelte";

vi.mock("$lib/daemon.svelte", () => ({ useDaemon: () => ({ client: {} }), resource: () => ({ data: undefined }) }));

describe("ApprovalModal", () => {
  it("shows a plugin the agent offers as its install", () => {
    const skill = {
      name: "notes",
      description: "Keep notes in a folder",
      files: [],
      installed: false,
      version: "",
      installed_version: "",
      category: "other/general",
    };
    const approval = { type: "ApprovalRequired" as const, interrupt_id: "i1", request: { kind: "plugin", name: "notes", skill } };
    const { body } = render(ApprovalModal, { props: { approval, onanswer: () => {} } });
    expect(body).toContain("Install notes");
    expect(body).not.toContain("Approve");
  });
});

describe("ApprovalModal for a plugin's setup", () => {
  it("opens the setup with a Done button", () => {
    const server: FoundServer = {
      name: "gmail",
      description: "Send and read Gmail",
      transport: "none",
      fields: [],
      trusted: false,
      skill: false,
      page: false,
      channel: false,
      email: true,
      category: "communications/email",
      model_login: "",
      ssh_agent: false,
      oauth: "",
      subagent: "",
      agent: "",
      installed: true,
      version: "1.0.0",
      installed_version: "1.0.0",
    };
    const approval = { type: "ApprovalRequired" as const, interrupt_id: "i1", request: { kind: "plugin_setup", name: "gmail", server } };
    const { body } = render(ApprovalModal, { props: { approval, onanswer: () => {} } });
    expect(body).toContain("Set up gmail");
    expect(body).toContain("Done");
  });
});
