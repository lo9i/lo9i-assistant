import { describe as group, expect, it } from "vitest";
import type { RepositoryContents } from "./api/types";
import { kindOf, pluginsOf, shortRepository } from "./plugins";

const contents: RepositoryContents = {
  skills: [{ name: "notes", description: "Notes", files: [], installed: false }],
  servers: [{ name: "expenses", description: "Bills", transport: "stdio", fields: [], trusted: false, skill: true, page: true, installed: true }],
};

group("pluginsOf", () => {
  it("lists servers, then skills, with their repository and state", () => {
    const plugins = pluginsOf([{ url: "https://github.com/lo9i/x", contents }]);
    expect(plugins.map((p) => [p.kind, p.name, p.installed])).toEqual([["server", "expenses", true], ["skill", "notes", false]]);
    expect(plugins.map(kindOf)).toEqual(["MCP server · skill · page", "Skill"]);
  });
});

group("shortRepository", () => {
  it("shortens GitHub addresses only", () => {
    expect(shortRepository("https://github.com/lo9i/lo9i-assistant-extras.git")).toBe("lo9i/lo9i-assistant-extras");
    expect(shortRepository("https://git.example.com/x/y")).toBe("git.example.com/x/y");
  });
});
