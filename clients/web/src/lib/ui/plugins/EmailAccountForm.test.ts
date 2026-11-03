import { render } from "svelte/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { EmailProvider } from "$lib/api/types";
import EmailAccountForm from "./EmailAccountForm.svelte";

// The email plugins' presets, as the daemon lists them.
const listed = vi.hoisted(() => ({ providers: [] as unknown[] }));
vi.mock("$lib/daemon.svelte", () => ({ useDaemon: () => ({ client: {} }), resource: () => ({ data: listed.providers }) }));

const microsoft: EmailProvider = {
  id: "microsoft",
  name: "Outlook.com / Microsoft 365",
  host: "smtp.office365.com",
  port: 587,
  imap_host: "outlook.office365.com",
  password_help: "Only if your organization blocks apps it hasn't approved: register your own.",
  password_url: "",
  supported: true,
  oauth: "microsoft",
  oauth_built_in: true,
  plugin: "microsoft",
  custom: false,
  translations: {},
};

function shown(provider: EmailProvider, hostname = "localhost"): string {
  listed.providers = [provider];
  vi.stubGlobal("window", { location: { protocol: "http:", hostname, origin: `http://${hostname}:8765` } });
  return render(EmailAccountForm, { props: { plugin: "microsoft", onsaved: () => {} } }).body;
}

describe("EmailAccountForm signing in with Microsoft", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("asks only for the address, with the user's own app behind a button", () => {
    const body = shown(microsoft);
    expect(body).toMatch(/There(&#39;|')s no app to register\./);
    expect(body).toContain("Sign in with Microsoft");
    expect(body).toContain("Use your own Microsoft app");
    expect(body).not.toContain("Client ID");
    expect(body).not.toContain("register your own");
  });

  it("says to open lo9i on its computer when it's open elsewhere", () => {
    const body = shown(microsoft, "board.ts.net");
    expect(body).toContain("can only send you back to lo9i on the computer it runs on");
    expect(body).toMatch(/<button class="btn btn--primary" type="submit" disabled/);
  });

  it("asks for the user's own app where lo9i has none", () => {
    // Its help is the plugin's Markdown, which needs a browser to clean; left out here.
    const body = shown({ ...microsoft, oauth: "google", oauth_built_in: false, password_help: "" });
    expect(body).toContain("Client ID");
    expect(body).toContain("Sign in with Google");
    expect(body).not.toContain("Use your own");
  });
});
