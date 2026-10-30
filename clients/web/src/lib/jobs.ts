// Scheduled jobs as text, like clients/terminal/src/assistant_terminal/jobs_text.py.
import cronstrue from "cronstrue";
import "cronstrue/locales/es";
import type { Job } from "./api/types";
import { language, t } from "./i18n.svelte";

/** How often it runs, in words: "Every day at 09:00", "At 08:00, Monday through Friday". */
export function every(job: Job): string {
  if (job.on_new_mail) return t("jobs.onEachEmail");
  if (job.one_time) return t("jobs.onceOn", { when: local(job.next_run_at, job.timezone) });
  try {
    const [minute, hour, day, month, weekday] = job.schedule.trim().split(/\s+/);
    const daily = day === "*" && month === "*" && weekday === "*" && /^\d+$/.test(minute) && /^\d+$/.test(hour);
    if (daily) return t("jobs.everyDayAt", { time: `${hour.padStart(2, "0")}:${minute.padStart(2, "0")}` });
    return cronstrue.toString(job.schedule, { use24HourTimeFormat: true, locale: language.locale });
  } catch {
    return job.schedule;
  }
}

/** When it runs, and whether it's on. */
export function summary(job: Job): string {
  return `${timing(job)} · ${state(job)}`;
}

export function timing(job: Job): string {
  if (job.on_new_mail) return t("jobs.onEachEmailLower");
  if (job.one_time) return t("jobs.onceAt", { when: local(job.next_run_at, job.timezone) });
  return `${job.schedule} (${job.timezone})`;
}

export function state(job: Job): string {
  if (job.enabled && job.on_new_mail) return t("jobs.waitingForMail");
  if (job.enabled) return t("jobs.next", { when: local(job.next_run_at, job.timezone) });
  return job.one_time && job.runs?.length ? t("jobs.done") : t("jobs.paused");
}

/** A time in the job's own time zone, like "Wed 30 Sep 09:00". */
export function local(timestamp: string, timezone: string): string {
  const parts = new Intl.DateTimeFormat(language.locale, {
    weekday: "short",
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
    timeZone: timezone,
  }).formatToParts(new Date(timestamp));
  const part = (type: string) => parts.find((p) => p.type === type)?.value ?? "";
  return `${part("weekday")} ${part("day")} ${part("month")} ${part("hour")}:${part("minute")}`;
}

/** The query of the Jobs page that opens a job's run, with its whole reply (a notification, a health check). */
export function runQuery(job: string, runAt: string): string {
  return `?job=${encodeURIComponent(job)}&run=${encodeURIComponent(runAt)}`;
}
