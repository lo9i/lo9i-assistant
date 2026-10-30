import type { PluginFieldValue, PluginSettingsChange } from "$lib/api/types";

/** What to send for an installed plugin's settings (PluginSettingsDialog): the fields not secret whose value
 * changed, the secret ones typed, and the secret ones to remove; null when nothing changed. A secret left empty is
 * left out, which keeps it. */
export function settingsChange(
  fields: PluginFieldValue[],
  typed: Record<string, string>,
  cleared: Set<string>,
): PluginSettingsChange | null {
  const values: Record<string, string> = {};
  for (const f of fields) {
    const value = (typed[f.key] ?? "").trim();
    if (f.secret ? value !== "" : value !== f.value) values[f.key] = value;
  }
  const clear = fields.filter((f) => f.secret && cleared.has(f.key) && !values[f.key]).map((f) => f.key);
  return Object.keys(values).length || clear.length ? { values, clear } : null;
}
