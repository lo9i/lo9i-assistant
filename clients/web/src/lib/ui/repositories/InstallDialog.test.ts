import { render } from "svelte/server";
import { describe, expect, it, vi } from "vitest";
import type { FoundServer } from "$lib/api/types";
import InstallDialog from "./InstallDialog.svelte";

vi.mock("$lib/daemon.svelte", () => ({ useDaemon: () => ({ client: {} }) }));

const telegram: FoundServer = {
  name: "telegram",
  description: "Chat with the assistant on Telegram",
  transport: "none",
  fields: [{ key: "TELEGRAM_TOKEN", label: "Bot token", secret: true, help: "https://t.me/BotFather" }],
  trusted: false,
  skill: false,
  page: false,
  channel: true,
  known_fields: ["TELEGRAM_TOKEN"],
  steps: ["Open @BotFather and send /newbot."],
  installed: false,
  version: "1.0.0",
  installed_version: "",
  category: "communications/chat",
  email: false,
};

describe("InstallDialog for one plugin", () => {
  it("shows its fields at once, without a checkbox", () => {
    const { body } = render(InstallDialog, { props: { server: telegram, onclose: () => {} } });
    expect(body).toContain("Install telegram");
    expect(body).toContain("Chat with the assistant on Telegram");
    expect(body).toContain("Bot token");
    expect(body).toContain("Leave empty to keep the one already saved");
    expect(body).toContain("t.me/BotFather");
    expect(body).toContain('<li class="text-label">Open @BotFather and send /newbot.</li>');
    expect(body).not.toContain('type="checkbox"');
  });
});

describe("InstallDialog for a skill the agent offers", () => {
  it("shows the skill and its files, with nothing to fill in", () => {
    const skill = {
      name: "notes",
      description: "Keep notes in a folder",
      files: ["scripts/add.py"],
      installed: false,
      version: "",
      installed_version: "",
      category: "other/general",
    };
    const { body } = render(InstallDialog, { props: { skill, onclose: () => {} } });
    expect(body).toContain("Install notes");
    expect(body).toContain("Keep notes in a folder");
    expect(body).toContain("Files: scripts/add.py");
    expect(body).not.toContain("<input");
  });
});
