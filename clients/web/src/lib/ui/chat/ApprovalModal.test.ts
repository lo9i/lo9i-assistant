import { render } from "svelte/server";
import { describe, expect, it, vi } from "vitest";
import type { ApprovalCall, FoundServer } from "$lib/api/types";
import ApprovalModal from "./ApprovalModal.svelte";

// The installed servers a resource reads, as the daemon lists them.
const installed = vi.hoisted(() => ({ servers: undefined as unknown }));
vi.mock("$lib/daemon.svelte", () => ({ useDaemon: () => ({ client: {} }), resource: () => ({ data: installed.servers }) }));

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
    const { body } = render(ApprovalModal, { props: { approval, onanswer: () => {}, onhide: () => {} } });
    expect(body).toContain("Install Notes");
    expect(body).not.toContain("Approve");
  });
});

describe("ApprovalModal for a plugin's setup", () => {
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
    login_session: false,
    oauth: "",
    subagent: "",
    check: false,
    agent: "",
    installed: true,
    version: "1.0.0",
    installed_version: "1.0.0",
  };

  it("opens the setup with a Done button", () => {
    const approval = { type: "ApprovalRequired" as const, interrupt_id: "i1", request: { kind: "plugin_setup", name: "gmail", server } };
    const { body } = render(ApprovalModal, { props: { approval, onanswer: () => {}, onhide: () => {} } });
    expect(body).toContain("Set up Gmail");
    expect(body).toContain("Done");
    expect(body).not.toContain("Settings");
  });

  it("offers its settings when the version installed has fields of its own", () => {
    installed.servers = [{ name: "gmail", settings: true }];
    const approval = { type: "ApprovalRequired" as const, interrupt_id: "i1", request: { kind: "plugin_setup", name: "gmail", server } };
    const { body } = render(ApprovalModal, { props: { approval, onanswer: () => {}, onhide: () => {} } });
    expect(body).toContain("Settings");
    installed.servers = undefined;
  });
});

describe("ApprovalModal for an MCP tool's call", () => {
  const ask = (call: ApprovalCall, command: string) => ({
    type: "ApprovalRequired" as const,
    interrupt_id: "i1",
    request: { tool: `mcp__${call.server}__${call.tool}`, command, reason: "billing isn't a trusted MCP server", call },
  });

  it("says what it does and what each argument is, with the exact call kept apart", () => {
    const call: ApprovalCall = {
      server: "billing",
      tool: "setup",
      does: "See or change the issuer's setup.",
      arguments: [{ name: "cuit", about: "The issuer's CUIT", value: "20-12345678-6" }],
      why: "untrusted",
    };
    const { body } = render(ApprovalModal, {
      props: { approval: ask(call, '{"cuit": "20-12345678-6"}'), onanswer: () => {}, onhide: () => {} },
    });
    expect(body).toContain("Approve setup from billing?");
    expect(body).toContain("billing isn't trusted, and this tool can change things.");
    expect(body).toContain("See or change the issuer's setup.");
    expect(body).toContain("The issuer's CUIT");
    expect(body).toContain("Exact call");
  });

  it("explains a call with no arguments and a tool that always asks", () => {
    const call: ApprovalCall = { server: "billing", tool: "create_invoice", does: "", arguments: [], why: "asks_first" };
    const { body } = render(ApprovalModal, { props: { approval: ask(call, "{}"), onanswer: () => {}, onhide: () => {} } });
    expect(body).toContain("No arguments: it runs with its defaults.");
    expect(body).toContain("billing asks before each use of this tool.");
  });
});

describe("ApprovalModal hidden without an answer", () => {
  const approval = { type: "ApprovalRequired" as const, interrupt_id: "i1", request: { tool: "bash", command: "rm -r build" } };
  const question = {
    type: "ApprovalRequired" as const,
    interrupt_id: "i2",
    request: { kind: "question", question: "Which one?", options: ["a", "b"] },
  };

  it("offers to hide an approval, which only its buttons answer", () => {
    const { body } = render(ApprovalModal, { props: { approval, onanswer: () => {}, onhide: () => {} } });
    expect(body).toContain('aria-label="Hide for now: nothing is answered, and the assistant keeps waiting"');
    expect(body).toContain("Reject");
    expect(body).toContain("Approve");
    expect(body).not.toMatch(/class="scrim[^"]*hidden/);
  });

  it("keeps a question hidden, with Skip as its own answer", () => {
    const { body } = render(ApprovalModal, { props: { approval: question, onanswer: () => {}, onhide: () => {}, hidden: true } });
    expect(body).toMatch(/class="scrim[^"]*hidden/);
    expect(body).toContain("Skip");
    expect(body).toContain("Hide for now");
  });

  it("declines a plugin offered with Don't install, not Cancel", () => {
    const skill = {
      name: "notes",
      description: "",
      files: [],
      installed: false,
      version: "",
      installed_version: "",
      category: "other/general",
    };
    const offer = { type: "ApprovalRequired" as const, interrupt_id: "i3", request: { kind: "plugin", name: "notes", skill } };
    const { body } = render(ApprovalModal, { props: { approval: offer, onanswer: () => {}, onhide: () => {} } });
    expect(body).toContain(">Don't install<");
    expect(body).not.toContain(">Cancel<");
  });
});
