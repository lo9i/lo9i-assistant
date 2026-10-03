import { describe, expect, it } from "vitest";
import type { McpToolInfo } from "./api/types";
import { selectionFor, parseArgs, parsePairs } from "./mcp";

const tool = (name: string): McpToolInfo => ({ name, description: "", read_only: false, selected: true });

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
