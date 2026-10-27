// Restarting or stopping the daemon from the Host card (src/assistant/daemon/shutdown.py). Either waits for
// the runs in progress to end; the page reloads once the daemon is back.

export type Ending = "restart" | "stop";

export const CONFIRM: Record<Ending, { title: string; text: string; action: string }> = {
  restart: {
    title: "Restart the assistant?",
    text: "It stops and starts again once the runs in progress end. This page reloads when it's back.",
    action: "Restart",
  },
  stop: {
    title: "Stop the assistant?",
    text:
      "Jobs, chat channels and the apps stop working until it's started again on the computer it runs on " +
      "(opening the terminal app there starts it). It waits for the runs in progress to end.",
    action: "Stop",
  },
};

/** A restart or stop the daemon accepted, until it's back: what it waits for, and whether it can be taken back (not
 * when something needs it, which `neededBy` says: an update installed, start at boot installed again). */
export type Coming = { ending: Ending; waiting: number; update: boolean; canTakeBack: boolean; neededBy: string };

/** From GET /system/ending (null when none is waiting) or an `ending` event (null when it was taken back). */
export function coming(data: Record<string, unknown>): Coming | null {
  if (!data.ending || data.taken_back) return null;
  return {
    ending: data.ending as Ending,
    waiting: Number(data.waiting_for_runs ?? 0),
    update: Boolean(data.waiting_for_update),
    canTakeBack: data.can_take_back !== false,
    neededBy: typeof data.needed_by === "string" ? data.needed_by : "",
  };
}

/** What the page says once the daemon has accepted the request, until it's back. */
export function endingText(c: Coming): string {
  if (c.ending === "restart") return `The assistant restarts ${when(c)}. This page reloads when it's back.`;
  return `The assistant stops ${when(c)}. Start it again on the computer it runs on; this page reloads when it's back.`;
}

/** While it waits: what Cancel and Now do, or why it can't be cancelled. */
export function waitingText(c: Coming): string {
  const does = c.ending === "restart" ? "restarts" : "stops";
  const now = c.waiting ? ` Now cancels the runs in progress, and it ${does} at once.` : "";
  if (c.canTakeBack) return `Cancel keeps the assistant running.${now}`;
  return `${c.neededBy || "Something needs it"}, so it can't be cancelled.${now}`;
}

/** Whether Cancel or Now has anything to do. */
export function answerable(c: Coming): { cancel: boolean; now: boolean } {
  return { cancel: c.canTakeBack && (c.waiting > 0 || c.update), now: c.waiting > 0 };
}

/** On every page, once any app asked for a restart or stop: what's coming and what it waits for. */
export function comingText(name: string, c: Coming): string {
  return `${name} ${c.ending === "restart" ? "restarts" : "stops"} ${when(c)}.`;
}

function when(c: Coming): string {
  const waits = [...(c.update ? ["the update being installed is done"] : []), ...(c.waiting ? [runs(c.waiting)] : [])];
  return waits.length ? `once ${waits.join(" and ")}` : "now";
}

function runs(count: number): string {
  return count === 1 ? "the run in progress ends" : `the ${count} runs in progress end`;
}
