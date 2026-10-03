import { describe as group, expect, it } from "vitest";
import type { RepositoryContents } from "./api/types";
import { kindOf, pluginsOf } from "./plugins";

const contents: RepositoryContents = {
  skills: [{ name: "notes", description: "Notes", files: [], installed: false }],
  servers: [{ name: "expenses", description: "Bills", transport: "stdio", fields: [], trusted: false, skill: true, page: true, installed: true }],
};

group("pluginsOf", () => {
  it("lists servers, then skills, with their state", () => {
    const plugins = pluginsOf(contents);
    expect(plugins.map((p) => [p.kind, p.name, p.installed])).toEqual([["server", "expenses", true], ["skill", "notes", false]]);
    expect(plugins.map(kindOf)).toEqual(["MCP server · skill · page", "Skill"]);
  });
});
