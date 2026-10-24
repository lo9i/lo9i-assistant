// Updating lo9i from the Host card (src/assistant/daemon/updates.py): what to say about the version it runs and
// what an update would bring.
import type { Commit, UpdateStatus } from "./api/types";

/** "a1b2c3d · Oct 24, 2026": the commit and its day. */
export function versionText(commit: Commit | null | undefined): string {
  if (!commit) return "Unknown";
  const day = new Date(commit.date).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
  return `${commit.sha.slice(0, 7)} · ${day}`;
}

/** One line on where the update stands: installing, failed, what's new, or why it can't be updated here. */
export function updateLine(status: UpdateStatus): string {
  if (status.state === "checking") return "Checking for updates…";
  if (status.state === "updating") return `${status.step}…`;
  if (status.state === "restarting") return "Installed. Restarting once the runs in progress end…";
  if (status.state === "failed") return status.error;
  if (status.reason) return status.reason;
  if (!status.checked_at) return "Not checked yet.";
  if (!status.behind) return `Up to date with ${status.upstream}.`;
  return `${status.behind} new ${status.behind === 1 ? "change" : "changes"} on ${status.upstream}.`;
}

/** Whether Update can be offered: a clone with something new and nothing in the way. */
export function canInstall(status: UpdateStatus): boolean {
  return status.can_update && status.behind > 0 && (status.state === "idle" || status.state === "failed");
}
