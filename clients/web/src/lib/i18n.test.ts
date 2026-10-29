import { describe, expect, it, vi } from "vitest";
import { formatDate, formatList, formatNumber, language, t } from "./i18n.svelte";
import en from "./locales/en.json";
import es from "./locales/es.json";

type Tree = { [key: string]: string | Tree };

/** Every text by its key; a plural's forms each a key of their own. */
function texts(tree: Tree, prefix = ""): Map<string, string> {
  const found = new Map<string, string>();
  for (const [key, value] of Object.entries(tree)) {
    if (typeof value === "string") found.set(prefix + key, value);
    else texts(value, `${prefix}${key}.`).forEach((text, inner) => found.set(inner, text));
  }
  return found;
}

function placeholders(text: string): string {
  return [...text.matchAll(/\{(\w+)\}/g)]
    .map((m) => m[1])
    .sort()
    .join();
}

describe("the languages' texts", () => {
  const english = texts(en);
  const spanish = texts(es);

  it("have the same keys in English and Spanish", () => {
    expect([...english.keys()].filter((key) => !spanish.has(key))).toEqual([]);
    expect([...spanish.keys()].filter((key) => !english.has(key))).toEqual([]);
  });

  it("fill in the same placeholders", () => {
    const differing = [...english].filter(([key, text]) => spanish.has(key) && placeholders(spanish.get(key)!) !== placeholders(text));
    expect(differing.map(([key]) => key)).toEqual([]);
  });

  it("are never empty", () => {
    expect([...english, ...spanish].filter(([, text]) => !text.trim()).map(([key]) => key)).toEqual([]);
  });
});

describe("t", () => {
  it("shows the language chosen, a count picking the plural form", () => {
    language.use("es");
    expect(t("common.cancel")).toBe("Cancelar");
    expect(t("duration.days", { count: 1 })).toBe("1 día");
    expect(t("duration.days", { count: 3 })).toBe("3 días");
    language.use("en");
    expect(t("conversations.today", { time: "09:00" })).toBe("Today 09:00");
    expect(t("duration.days", { count: 1 })).toBe("1 day");
  });

  it("follows the browser's language until one is picked: Spanish for any Spanish, else English", () => {
    for (const [browser, shown] of [
      ["es-AR", "es"],
      ["es", "es"],
      ["en-US", "en"],
      ["pt-BR", "en"],
    ]) {
      vi.stubGlobal("navigator", { language: browser });
      language.use("en");
      language.use("auto");
      expect(language.locale).toBe(shown);
    }
    vi.unstubAllGlobals();
    language.use("en");
  });

  it("writes dates, numbers and lists as the language does", () => {
    const day = new Date("2026-10-29T12:00:00Z");
    language.use("es");
    expect(formatNumber(23610)).toBe("23.610");
    expect(formatList(["a", "b", "c"])).toBe("a, b y c");
    expect(formatDate(day, { month: "long", timeZone: "UTC" })).toBe("octubre");
    language.use("en");
    expect(formatNumber(23610)).toBe("23,610");
    expect(formatList(["a", "b", "c"])).toBe("a, b and c");
  });
});
