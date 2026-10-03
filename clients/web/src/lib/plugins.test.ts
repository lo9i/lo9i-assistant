import { describe as group, expect, it } from "vitest";
import type { RepositoryContents } from "./api/types";
import { kindOf, pluginsOf, versionOf } from "./plugins";

const contents: RepositoryContents = {
  skills: [{ name: "notes", description: "Notes", files: [], installed: false, version: "", installed_version: "" }],
  servers: [
    { name: "expenses", description: "Bills", transport: "stdio", fields: [], trusted: false, skill: true, page: true, installed: true, version: "", installed_version: "" },
  ],
};

group("pluginsOf", () => {
  it("lists servers, then skills, with their state", () => {
    const plugins = pluginsOf(contents);
    expect(plugins.map((p) => [p.kind, p.name, p.installed])).toEqual([["server", "expenses", true], ["skill", "notes", false]]);
    expect(plugins.map(kindOf)).toEqual(["MCP server · skill · page", "Skill"]);
  });
});

group("versionOf", () => {
  it("shows what's installed and what's newer", () => {
    const server = (version: string, installed_version: string, installed: boolean) =>
      pluginsOf({ skills: [], servers: [{ name: "x", description: "", transport: "stdio", fields: [], trusted: false, skill: false, page: false, version, installed_version, installed }] })[0];
    expect(versionOf(server("1.1.0", "1.0.0", true))).toBe("1.0.0 → 1.1.0");
    expect(versionOf(server("1.1.0", "1.1.0", true))).toBe("1.1.0");
    expect(versionOf(server("1.1.0", "", false))).toBe("1.1.0");
    expect(versionOf(server("", "", false))).toBe("–");
  });
});
