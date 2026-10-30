import { describe as group, expect, it } from "vitest";
import type { FoundServer, RepositoryContents } from "./api/types";
import {
  byCategory,
  categoryLabel,
  emptyHint,
  fromRepositories,
  hasSetup,
  kindOf,
  missingField,
  optional,
  pluginsOf,
  runsOf,
  sharedLogin,
  sshAgentNote,
  hasNewer,
  updatable,
  versionOf,
} from "./plugins";

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
      model_login: "",
      ssh_agent: false,
      oauth: "",
      subagent: "",
      agent: "",
      email: false,
    },
  ],
  checked: "",
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
            model_login: "",
            ssh_agent: false,
            oauth: "",
            subagent: "",
            agent: "",
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
          model_login: "",
          ssh_agent: false,
          oauth: "",
          subagent: "",
          agent: "",
          email: false,
        },
      ],
    })[0];
  it("offers Update only when the extras have another version, or none is declared", () => {
    expect(updatable(server("0.2.1", "0.2.1", true))).toBe(false);
    expect(updatable(server("0.3.0", "0.2.1", true))).toBe(true);
    expect(updatable(server("", "", true))).toBe(true);
    expect(updatable(server("0.3.0", "", false))).toBe(false);
  });

  it("lists as newer only a declared version that differs from the installed one", () => {
    expect(hasNewer(server("0.3.0", "0.2.1", true))).toBe(true);
    expect(hasNewer(server("0.2.1", "0.2.1", true))).toBe(false);
    expect(hasNewer(server("", "", true))).toBe(false);
    expect(hasNewer(server("0.3.0", "", false))).toBe(false);
  });
});

const found = (over: Partial<FoundServer>): FoundServer => ({
  name: "telegram",
  description: "Chat on Telegram",
  transport: "none",
  fields: [{ key: "BOT_TOKEN", label: "Bot token", secret: true, help: "", optional: false }],
  trusted: true,
  skill: false,
  page: false,
  channel: true,
  installed: false,
  version: "",
  installed_version: "",
  category: "other/general",
  model_login: "",
  ssh_agent: false,
  oauth: "",
  subagent: "",
  agent: "",
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

  it("label an email provider", () => {
    const gmail = found({ name: "gmail", channel: false, email: true, category: "communications/email" });
    expect(pluginsOf({ skills: [], servers: [gmail] }).map(kindOf)).toEqual(["Email provider"]);
  });

  it("label a subagent", () => {
    const researcher = found({ name: "researcher", transport: "none", channel: false, subagent: "researcher" });
    expect(pluginsOf({ skills: [], servers: [researcher] }).map(kindOf)).toEqual(["Subagent"]);
  });

  it("label a coding agent, not as the skill that comes with it", () => {
    const claude = found({ name: "claude-code", transport: "none", channel: false, skill: true, agent: "claude" });
    expect(pluginsOf({ skills: [], servers: [claude] }).map(kindOf)).toEqual(["Coding agent · skill"]);
  });

  it("have a setup, as email plugins and plugins that sign in do", () => {
    expect(hasSetup(found({}))).toBe(true);
    expect(hasSetup(found({ channel: false, email: true }))).toBe(true);
    expect(hasSetup(found({ channel: false, transport: "stdio", oauth: "google" }))).toBe(true);
    expect(hasSetup(found({ channel: false, transport: "stdio" }))).toBe(false);
  });

  it("may leave empty a value the daemon already has", () => {
    const known = found({ known_fields: ["BOT_TOKEN"] });
    expect(optional(known, "BOT_TOKEN")).toBe(true);
    expect(missingField(known, { BOT_TOKEN: "" })).toBeNull();
    expect(missingField(found({}), { BOT_TOKEN: " " })).toBe("Bot token");
    expect(missingField(found({}), { BOT_TOKEN: "123:abc" })).toBeNull();
  });
});

group("emptyHint and sharedLogin", () => {
  const coder = found({
    name: "claude-code",
    fields: [{ key: "CLAUDE_TOKEN", label: "Claude token", secret: true, help: "", optional: true }],
    known_fields: [],
    model_login: "copilot",
    ssh_agent: false,
    oauth: "",
    subagent: "",
  });
  it("says a field may be left empty", () => {
    expect(optional(coder, "CLAUDE_TOKEN")).toBe(true);
    expect(emptyHint(coder, "CLAUDE_TOKEN")).toBe("Optional");
    expect(missingField(coder, { CLAUDE_TOKEN: "" })).toBeNull();
    expect(emptyHint(found({}), "BOT_TOKEN")).toBe("");
  });
  it("says when the plugin uses the Copilot login", () => {
    expect(sharedLogin(coder)).toContain("GitHub Copilot login");
    expect(sharedLogin(found({}))).toBe("");
  });
  it("says when the plugin uses the ssh agent", () => {
    expect(sshAgentNote(found({ ssh_agent: true }))).toContain("ssh agent");
    expect(sshAgentNote(found({}))).toBe("");
  });
});

group("fromRepositories", () => {
  it("lists the plugins it could read and says which it couldn't, and which repositories", () => {
    const extras = {
      url: "https://github.com/lo9i/lo9i-assistant-extras",
      name: "lo9i/lo9i-assistant-extras",
      official: true,
      private: false,
    };
    const mine = { url: "https://github.com/me/plugins", name: "me/plugins", official: false, private: false };
    const read = fromRepositories([
      { repository: extras, contents: { ...contents, problems: ["apps/finance/ledger/server.yaml can't be used: bad"] }, error: "" },
      { repository: mine, contents: null, error: "Couldn't get the repository" },
    ]);
    expect(read.plugins.map((p) => p.name)).toEqual(["expenses", "notes"]);
    expect(read.errors).toEqual([
      "me/plugins: Couldn't get the repository",
      "lo9i/lo9i-assistant-extras: apps/finance/ledger/server.yaml can't be used: bad",
    ]);
  });

  it("was checked when its least recently checked repository was, and not while one never was", () => {
    const repository = (name: string) => ({ url: `https://github.com/${name}`, name, official: false, private: false });
    const at = (name: string, checked: string) => ({ repository: repository(name), contents: { ...contents, checked }, error: "" });
    expect(fromRepositories([at("a", "2026-10-24T10:00:00Z"), at("b", "2026-10-24T09:00:00Z")]).checked).toBe("2026-10-24T09:00:00Z");
    expect(fromRepositories([at("a", "2026-10-24T10:00:00Z"), at("b", "")]).checked).toBe("");
    expect(fromRepositories([at("a", "2026-10-24T10:00:00Z"), { repository: repository("b"), contents: null, error: "x" }]).checked).toBe(
      "",
    );
  });
});
