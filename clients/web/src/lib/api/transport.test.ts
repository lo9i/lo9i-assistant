import { afterEach, describe, expect, it, vi } from "vitest";
import { language } from "../i18n.svelte";
import { HttpTransport } from "./transport";

afterEach(() => {
  vi.unstubAllGlobals();
  language.use("auto");
});

describe("HttpTransport", () => {
  it("tells the daemon the language the app shows, as it is at each request", async () => {
    const fetch = vi.fn().mockImplementation(async () => new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetch);
    const transport = new HttpTransport("me");
    language.use("es");
    await transport.request("GET", "/jobs");
    language.use("en");
    await transport.request("GET", "/jobs");
    const sent = fetch.mock.calls.map(([, init]) => (init as RequestInit).headers as Record<string, string>);
    expect(sent.map((headers) => headers["X-Lo9i-Language"])).toEqual(["es", "en"]);
    expect(sent[0]["X-Lo9i-Client-Id"]).toBe("me");
  });
});
