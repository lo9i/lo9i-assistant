import { render } from "svelte/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import { language } from "$lib/i18n.svelte";
import LanguageCard from "./LanguageCard.svelte";

vi.mock("$lib/daemon.svelte", () => ({
  useDaemon: () => ({ client: {}, notices: {} }),
  resource: () => ({ data: { language: "es" } }),
}));

describe("LanguageCard", () => {
  afterEach(() => language.use("en"));

  it("shows the language the daemon keeps, the card in the language shown", () => {
    language.use("es");
    const { body } = render(LanguageCard);
    expect(body).toContain("Idioma");
    expect(body).toContain("Automático (el idioma de este navegador)");
    expect(body).toMatch(/<option value="es"[^>]*selected/);
    expect(body).not.toMatch(/<option value="auto"[^>]*selected/);
  });
});
