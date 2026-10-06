import { describe, expect, it } from "vitest";
import { agentCommands, known, offered, parse } from "./commands";

describe("commands", () => {
  it("offers commands while the name is typed", () => {
    expect(offered("/").length).toBeGreaterThan(10);
    expect(offered("/s").map((c) => c.name)).toEqual(["/sessions", "/settings", "/skills", "/startup"]);
    expect(offered("/name Max")).toEqual([]);
    expect(offered("hello")).toEqual([]);
  });

  it("splits a command line", () => {
    expect(parse("/name  Max Power ")).toEqual({ name: "/name", arg: "Max Power" });
    expect(parse("/new")).toEqual({ name: "/new", arg: "" });
    expect(parse("hello /new")).toBeNull();
    expect(known("/jobs") && !known("/mouse")).toBe(true);
  });
});

describe("agent commands", () => {
  const claude = { server: "claude-code", command: "claude", name: "Claude Code", tool: "converse" };
  it("adds a command per agent, never hiding a built-in one", () => {
    const extra = agentCommands([claude, { ...claude, command: "new" }]);
    expect(extra.map((c) => c.name)).toEqual(["/claude"]);
    expect(extra[0].usage).toBe("/claude <folder> | off");
    expect(offered("/cl", extra).map((c) => c.name)).toEqual(["/claude"]);
    expect(offered("/cl").map((c) => c.name)).toEqual([]);
  });
});
