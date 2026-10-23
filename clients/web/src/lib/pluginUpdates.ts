import { type Plugin, keyOf } from "./plugins";

/** Where a plugin picked for an update is: its turn to come, updating now, or how it went. */
export type UpdateStep = "waiting" | "updating" | "updated" | "failed";

/**
 * Update the plugins one after the other, since an update restarts the plugin; one that fails doesn't stop the
 * rest. `onstep` hears every plugin's step by its key (keyOf), every one waiting first, so a page can show each
 * row's progress. Returns the names of those updated and those that failed.
 */
export async function updateEach(
  picked: Plugin[],
  updateOne: (p: Plugin) => Promise<unknown>,
  onstep: (key: string, step: UpdateStep) => void,
  onerror: (e: unknown) => void = () => {},
): Promise<{ updated: string[]; failed: string[] }> {
  const updated: string[] = [];
  const failed: string[] = [];
  for (const p of picked) onstep(keyOf(p), "waiting");
  for (const p of picked) {
    onstep(keyOf(p), "updating");
    try {
      await updateOne(p);
      updated.push(p.name);
      onstep(keyOf(p), "updated");
    } catch (e) {
      failed.push(p.name);
      onstep(keyOf(p), "failed");
      onerror(e);
    }
  }
  return { updated, failed };
}
