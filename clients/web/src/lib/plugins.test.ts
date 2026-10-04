import { describe as group, expect, it } from "vitest";
import type { FoundServer, RepositoryContents } from "./api/types";
import { byCategory, categoryLabel, hasSettings, kindOf, missingField, optional, pluginsOf, runsOf, updatable, versionOf } from "./plugins";

const contents: RepositoryContents = {
  skills: [
    {
      name: "notes",
      description: "Notes",
      files: [],
      installed: false,
      version: "",
      installed_version: "",
      category: "other/general",
    },
  ],
  servers: [
    {
      name: "expenses",
      description: "Bills",
      transport: "stdio",
      fields: [],
      trusted: false,
      skill: true,
      page: true,
      channel: false,
      installed: true,
      version: "",
      installed_version: "",
      category: "other/general",
      email: false,
    },
  ],
};

group("pluginsOf", () => {
  it("lists servers, then skills, with their state", () => {
    const plugins = pluginsOf(contents);
    expect(plugins.map((p) => [p.kind, p.name, p.installed])).toEqual([
      ["server", "expenses", true],
      ["skill", "notes", false],
    ]);
    expect(plugins.map(kindOf)).toEqual(["MCP server · skill · page", "Skill"]);
  });
});

group("byCategory", () => {
  it("groups by the category's group, alphabetically with other last", () => {
    const server = (name: string, category = "other/general"): FoundServer => ({ ...contents.servers[0], name, category });
    const plugins = pluginsOf({
      skills: contents.skills,
      servers: [
        server("ledger", "apps/finance"),
        server("bot", "communications/chat"),
        server("mail", "communications/email"),
        server("misc"),
      ],
    });
    expect(byCategory(plugins).map((g) => [g.category, g.plugins.map((p) => p.name)])).toEqual([
      ["apps", ["ledger"]],
      ["communications", ["bot", "mail"]],
      ["other", ["misc", "notes"]],
    ]);
    expect([categoryLabel("communications"), categoryLabel("communications/email")]).toEqual(["Communications", "Communications / Email"]);
  });
});

group("versionOf", () => {
  it("shows what's installed and what's newer", () => {
    const server = (version: string, installed_version: string, installed: boolean) =>
      pluginsOf({
        skills: [],
        servers: [
          {
            name: "x",
            description: "",
            transport: "stdio",
            fields: [],
            trusted: false,
            skill: false,
            page: false,
            channel: false,
            version,
            installed_version,
            installed,
            category: "other/general",
            email: false,
          },
        ],
      })[0];
    expect(versionOf(server("1.1.0", "1.0.0", true))).toBe("1.0.0 → 1.1.0");
    expect(versionOf(server("1.1.0", "1.1.0", true))).toBe("1.1.0");
    expect(versionOf(server("1.1.0", "", false))).toBe("1.1.0");
    expect(versionOf(server("", "", false))).toBe("–");
  });
});

group("updatable", () => {
  it("offers Update only when the extras have another version, or none is declared", () => {
    const server = (version: string, installed_version: string, installed: boolean) =>
      pluginsOf({
        skills: [],
        servers: [
          {
            name: "x",
            description: "",
            transport: "stdio",
            fields: [],
            trusted: false,
            skill: false,
            page: false,
            channel: false,
            version,
            installed_version,
            installed,
            category: "other/general",
            email: false,
          },
        ],
      })[0];
    expect(updatable(server("0.2.1", "0.2.1", true))).toBe(false);
    expect(updatable(server("0.3.0", "0.2.1", true))).toBe(true);
    expect(updatable(server("", "", true))).toBe(true);
    expect(updatable(server("0.3.0", "", false))).toBe(false);
  });
});

const found = (over: Partial<FoundServer>): FoundServer => ({
  name: "telegram",
  description: "Chat on Telegram",
  transport: "none",
  fields: [{ key: "BOT_TOKEN", label: "Bot token", secret: true, help: "" }],
  trusted: true,
  skill: false,
  page: false,
  channel: true,
  installed: false,
  version: "",
  installed_version: "",
  category: "other/general",
  email: false,
  ...over,
});

group("channel plugins", () => {
  it("are labelled as channels", () => {
    const kinds = pluginsOf({ skills: [], servers: [found({}), found({ name: "slack", transport: "stdio", skill: true })] }).map(kindOf);
    expect(kinds).toEqual(["Channel", "MCP server · channel · skill"]);
    expect(runsOf(found({}))).toBe("On the assistant's computer");
    expect(runsOf(found({ transport: "http" }))).toBe("Remotely");
  });

  it("label an email provider, and only Communications has shared settings", () => {
    const gmail = found({ name: "gmail", channel: false, email: true, category: "communications/email" });
    expect(pluginsOf({ skills: [], servers: [gmail] }).map(kindOf)).toEqual(["Email provider"]);
    expect([hasSettings("communications"), hasSettings("finance")]).toEqual([true, false]);
  });

  it("may leave empty a value the daemon already has", () => {
    const known = found({ known_fields: ["BOT_TOKEN"] });
    expect(optional(known, "BOT_TOKEN")).toBe(true);
    expect(missingField(known, { BOT_TOKEN: "" })).toBeNull();
    expect(missingField(found({}), { BOT_TOKEN: " " })).toBe("Bot token");
    expect(missingField(found({}), { BOT_TOKEN: "123:abc" })).toBeNull();
  });
});
