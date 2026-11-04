// Home's Open loops card (core/home/loops.py): what's still to do or waiting, but bills due, which the Expenses card
// shows.
import type { OpenLoop } from "./api/types";

/** The Open loops card's id (LOOPS in core/home/sections.py): the app draws it live from the loops instead of from
 * its result. */
export const LOOPS = "loops";
/** The kind of the loops left out (BILL_DUE in core/home/loops.py). */
export const BILL_DUE = "bill due";

/** The open ones but bills: those with a due day first, the soonest first, then the rest as given (newest first). */
export function homeLoops(loops: readonly OpenLoop[]): OpenLoop[] {
  const listed = loops.filter((l) => (l.status ?? "open") === "open" && l.kind !== BILL_DUE);
  const dated = listed.filter((l) => l.due).sort((a, b) => (a.due ?? "").localeCompare(b.due ?? ""));
  return [...dated, ...listed.filter((l) => !l.due)];
}
