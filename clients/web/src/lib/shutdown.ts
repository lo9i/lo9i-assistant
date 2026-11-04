// Restarting or stopping the daemon from the Assistant card (src/assistant/daemon/shutdown.py). Either waits for
// the runs in progress to end; the page reloads once the daemon is back.
import { formatDate, formatList, t } from "./i18n.svelte";

export type Ending = "restart" | "stop";

/** What the Assistant card asks before a restart or stop. */
export function confirmation(ending: Ending): { title: string; text: string; action: string } {
  if (ending === "restart") {
    return { title: t("shutdown.restartTitle"), text: t("shutdown.restartText"), action: t("shutdown.restart") };
  }
  return { title: t("shutdown.stopTitle"), text: t("shutdown.stopText"), action: t("shutdown.stop") };
}

/** A restart or stop the daemon accepted, until it's back: what it waits for, and whether it can be taken back (not
 * when something needs it, which `neededBy` says: an update installed, start at boot installed again). `askedBy` and
 * `askedAt` say who asked and when, `queued` how many messages queued in conversations (a coding task, a follow-up)
 * wait for it; GET /system/ending says them, an `ending` event doesn't. */
export type Coming = {
  ending: Ending;
  waiting: number;
  update: boolean;
  canTakeBack: boolean;
  neededBy: string;
  askedBy?: string;
  askedAt?: string;
  queued?: number;
};

/** From GET /system/ending (null when none is waiting) or an `ending` event (null when it was taken back). */
export function coming(data: Record<string, unknown>): Coming | null {
  if (!data.ending || data.taken_back) return null;
  return {
    ending: data.ending as Ending,
    waiting: Number(data.waiting_for_runs ?? 0),
    update: Boolean(data.waiting_for_update),
    canTakeBack: data.can_take_back !== false,
    neededBy: typeof data.needed_by === "string" ? data.needed_by : "",
    ...(typeof data.asked_by === "string" && data.asked_by ? { askedBy: data.asked_by } : {}),
    ...(typeof data.asked_at === "string" && data.asked_at ? { askedAt: data.asked_at } : {}),
    ...(typeof data.queued_messages === "number" ? { queued: data.queued_messages } : {}),
  };
}

/** Which notice every page shows: the daemon away (`lost`, while a restart or stop of it or anything else), a restart
 * or stop coming, or a new build of the page; "" for none. A notice the user dismissed stays away until this changes. */
export function noticeShown(lost: boolean, c: Coming | null, newVersion: boolean): string {
  if (lost) return `lost:${c?.ending ?? ""}`;
  if (c) return `coming:${c.ending}`;
  return newVersion ? "fresh" : "";
}

/** The notice still put away: only while the same one shows. Once it says something else (a restart taken back,
 * the New version notice under it showing), it's forgotten, so a restart asked for later shows again. */
export function stillPutAway(shown: string, dismissed: string): string {
  return shown === dismissed ? dismissed : "";
}

/** The pending restart or stop as a title, for the notice every page shows. */
export function pendingTitle(c: Coming): string {
  return c.ending === "restart" ? t("shutdown.restartPending") : t("shutdown.stopPending");
}

/** Who asked and when, and the queued messages that wait for it; "" when the daemon didn't say. */
export function pendingDetail(c: Coming): string {
  const parts: string[] = [];
  if (c.askedBy && c.askedAt) {
    const at = formatDate(c.askedAt, { hour: "2-digit", minute: "2-digit" });
    parts.push(t("shutdown.askedBy", { by: c.askedBy, at }));
  }
  if (c.queued) parts.push(t("shutdown.queuedWait", { count: c.queued }));
  return parts.join(" ");
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
