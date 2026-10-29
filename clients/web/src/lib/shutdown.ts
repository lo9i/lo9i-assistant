// Restarting or stopping the daemon from the Host card (src/assistant/daemon/shutdown.py). Either waits for
// the runs in progress to end; the page reloads once the daemon is back.
import { formatList, t } from "./i18n.svelte";

export type Ending = "restart" | "stop";

/** What the Host card asks before a restart or stop. */
export function confirmation(ending: Ending): { title: string; text: string; action: string } {
  if (ending === "restart") {
    return { title: t("shutdown.restartTitle"), text: t("shutdown.restartText"), action: t("shutdown.restart") };
  }
  return { title: t("shutdown.stopTitle"), text: t("shutdown.stopText"), action: t("shutdown.stop") };
}

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
  return c.ending === "restart" ? t("shutdown.restarting", { when: when(c) }) : t("shutdown.stopping", { when: when(c) });
}

/** While it waits: what Cancel and Now do, or why it can't be cancelled. */
export function waitingText(c: Coming): string {
  const now = c.waiting ? " " + (c.ending === "restart" ? t("shutdown.nowRestarts") : t("shutdown.nowStops")) : "";
  if (c.canTakeBack) return t("shutdown.cancelKeeps") + now;
  return t("shutdown.cantCancel", { neededBy: c.neededBy || t("shutdown.somethingNeedsIt") }) + now;
}

/** Whether Cancel or Now has anything to do. */
export function answerable(c: Coming): { cancel: boolean; now: boolean } {
  return { cancel: c.canTakeBack && (c.waiting > 0 || c.update), now: c.waiting > 0 };
}

/** On every page, once any app asked for a restart or stop: what's coming and what it waits for. */
export function comingText(name: string, c: Coming): string {
  const values = { name, when: when(c) };
  return c.ending === "restart" ? t("shutdown.nameRestarts", values) : t("shutdown.nameStops", values);
}

function when(c: Coming): string {
  const waits = [...(c.update ? [t("shutdown.updateDone")] : []), ...(c.waiting ? [t("shutdown.runsEnd", { count: c.waiting })] : [])];
  return waits.length ? t("shutdown.once", { waits: formatList(waits) }) : t("shutdown.now");
}
