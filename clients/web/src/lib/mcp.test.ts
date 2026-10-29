import { describe, expect, it } from "vitest";
import type { McpServerStatus, McpToolInfo } from "./api/types";
import { selectionFor, parseArgs, parsePairs, statusLabel, trustText, withTools } from "./mcp";

const tool = (name: string, asks_first = false): McpToolInfo => ({ name, description: "", read_only: false, selected: true, asks_first });

describe("parsePairs", () => {
  it("reads env and header lines", () => {
    expect(parsePairs("A=1\n\n B = x=y ", "=")).toEqual({ A: "1", B: "x=y" });
    expect(parsePairs("Authorization: Bearer t", ":")).toEqual({ Authorization: "Bearer t" });
  });
  it("rejects a line without a name", () => {
    expect(() => parsePairs("=1", "=")).toThrow();
    expect(() => parsePairs("token", ":")).toThrow();
  });
});

describe("parseArgs", () => {
  it("splits one line on spaces and keeps lines otherwise", () => {
    expect(parseArgs("-y @scope/server /tmp")).toEqual(["-y", "@scope/server", "/tmp"]);
    expect(parseArgs("--dir\n/my files\n")).toEqual(["--dir", "/my files"]);
    expect(parseArgs("")).toEqual([]);
  });
});

describe("selectionFor", () => {
  const tools = [tool("a"), tool("b")];
  it("has no filter when every tool is chosen", () => {
    expect(selectionFor(tools, new Set(["a", "b"]))).toEqual({ include: [], exclude: [] });
  });
  it("includes the chosen ones", () => {
    expect(selectionFor(tools, new Set(["b"]))).toEqual({ include: ["b"], exclude: [] });
  });
  it("excludes everything when none is chosen", () => {
    expect(selectionFor(tools, new Set())).toEqual({ include: [], exclude: ["*"] });
  });
});

describe("statusLabel", () => {
  it("spells out a server waiting for a sign-in and keeps the other words", () => {
    expect(statusLabel("needs_sign_in")).toBe("needs you to sign in");
    expect(statusLabel("idle")).toBe("starts when used");
    expect(statusLabel("connected")).toBe("connected");
  });
});

describe("withTools", () => {
  it("leaves out a plugin without tools, and keeps Slack, which has tools too", () => {
    const server = (name: string, transport: string, channel: boolean) => ({ name, transport, channel }) as McpServerStatus;
    const servers = [server("notes", "stdio", false), server("telegram", "none", true), server("slack", "stdio", true)];
    expect(withTools(servers).map((s) => s.name)).toEqual(["notes", "slack"]);
  });
});

describe("trustText", () => {
  it("says which tools of a trusted server still ask", () => {
    const server = (trusted: boolean, tools: McpToolInfo[]) => ({ trusted, tools }) as McpServerStatus;
    expect(trustText(server(true, [tool("read")]))).toBe("Its tools run without asking.");
    expect(trustText(server(true, [tool("read"), tool("download", true)]))).toContain("but those marked asks first");
    expect(trustText(server(false, [tool("download", true)]))).toContain("asks for approval first");
  });
});
