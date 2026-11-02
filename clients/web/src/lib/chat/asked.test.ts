import { describe, expect, it } from "vitest";
import { askTitle } from "./asked";

describe("askTitle", () => {
  it("names each kind of ask as its dialog is titled", () => {
    expect(askTitle({ kind: "question", question: "Which one?" })).toBe("Which one?");
    expect(askTitle({ kind: "question" })).toBe("Pick one");
    expect(askTitle({ kind: "form", asked_by: "billing" })).toBe("billing asks");
    expect(askTitle({ kind: "plugin", name: "telegram" })).toBe("Install Telegram");
    expect(askTitle({ kind: "plugin_setup", name: "gmail" })).toBe("Set up Gmail");
    expect(askTitle({ tool: "bash" })).toBe("Approve bash?");
    expect(askTitle({})).toBe("Approve this action?");
  });

  it("names an MCP tool's call by its tool and server", () => {
    const call = { server: "billing", tool: "setup", does: "", arguments: [], why: "untrusted" as const };
    expect(askTitle({ tool: "mcp__billing__setup", call })).toBe("Approve setup from billing?");
  });
});
