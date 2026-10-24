import { DaemonUnavailableError } from "./api/errors";
import { type Plugin, keyOf } from "./plugins";

/** The background check of the repositories: running, or failed (the list kept from the last read stays). */
export type CheckState = "idle" | "checking" | "failed";

/**
 * Read the repositories for what changed since they were last read. The page shows the kept listing meanwhile; a
 * read that finds something new saves it, which the daemon announces as `plugins`, so the page loads it then.
 * An unreachable daemon isn't this check's failure: the app says so for every page.
 */
export async function checkRepositories(read: () => Promise<unknown>, onstate: (state: CheckState) => void): Promise<void> {
  onstate("checking");
  try {
    await read();
    onstate("idle");
  } catch (e) {
    onstate(e instanceof DaemonUnavailableError ? "idle" : "failed");
  }
}

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
