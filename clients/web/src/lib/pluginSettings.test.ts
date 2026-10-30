import { describe as group, expect, it } from "vitest";
import type { PluginFieldValue } from "$lib/api/types";
import { settingsChange } from "./pluginSettings";

const field = (key: string, secret: boolean, value = "", set = true): PluginFieldValue => ({
  key,
  label: key,
  secret,
  help: "",
  optional: true,
  value,
  set,
});

const fields = [field("URL", false, "https://a"), field("USER", false, "me"), field("PASSWORD", true)];

group("settingsChange", () => {
  it("sends only the fields that changed and the secrets typed", () => {
    const typed = { URL: "https://b ", USER: "me", PASSWORD: "" };
    expect(settingsChange(fields, typed, new Set())).toEqual({ values: { URL: "https://b" }, clear: [] });
    expect(settingsChange(fields, { ...typed, PASSWORD: "new" }, new Set())?.values).toEqual({ URL: "https://b", PASSWORD: "new" });
  });

  it("empties a field not secret, and a secret one only when cleared", () => {
    expect(settingsChange(fields, { URL: "", USER: "me", PASSWORD: "" }, new Set())).toEqual({ values: { URL: "" }, clear: [] });
    expect(settingsChange(fields, { URL: "https://a", USER: "me", PASSWORD: "" }, new Set(["PASSWORD"]))).toEqual({
      values: {},
      clear: ["PASSWORD"],
    });
  });

  it("is nothing when nothing changed", () => {
    expect(settingsChange(fields, { URL: "https://a", USER: "me", PASSWORD: "" }, new Set())).toBeNull();
  });
});
