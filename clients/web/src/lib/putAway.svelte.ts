// The notice every page shows (ConnectionBanner) once the user put it away: what it said, for the badge on the
// assistant's mark in the sidebar, which brings it back. Null while none is put away.

/** `fresh`: a new build of the page; `stop` and `restart`: one coming; `lost`: the daemon away. `label` says it in a
 * word or two, `waiting` how many runs a restart or stop still waits for. */
export type PutAway = { kind: "restart" | "stop" | "lost" | "fresh"; label: string; waiting: number };

class PutAwayNotice {
  current = $state<PutAway | null>(null);
  // Set by the notice: shows it again.
  reopen: () => void = () => {};
}

export const putAway = new PutAwayNotice();
