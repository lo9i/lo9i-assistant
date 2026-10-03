// Scheduled jobs as text, like src/assistant/gateways/cli/jobs_text.py.
import cronstrue from "cronstrue";
import type { Job } from "./api/types";

/** How often it runs, in words: "Every day at 09:00", "At 08:00, Monday through Friday". */
export function every(job: Job): string {
  if (job.on_new_mail) return "On each new email";
  if (job.one_time) return `Once, on ${local(job.next_run_at, job.timezone)}`;
  try {
    const text = cronstrue.toString(job.schedule, { use24HourTimeFormat: true });
    const [, , day, month, weekday] = job.schedule.trim().split(/\s+/);
    const daily = day === "*" && month === "*" && weekday === "*" && text.startsWith("At ");
    return daily ? `Every day at ${text.slice(3)}` : text;
  } catch {
    return job.schedule;
  }
}

/** When it runs, and whether it's on. */
export function summary(job: Job): string {
  return `${timing(job)} · ${state(job)}`;
}

export function timing(job: Job): string {
  if (job.on_new_mail) return "on each new email";
  if (job.one_time) return `once at ${local(job.next_run_at, job.timezone)}`;
  return `${job.schedule} (${job.timezone})`;
}

export function state(job: Job): string {
  if (job.enabled && job.on_new_mail) return "waiting for mail";
  if (job.enabled) return `next ${local(job.next_run_at, job.timezone)}`;
  return job.one_time && job.runs?.length ? "done" : "paused";
}

/** A time in the job's own time zone, like "Wed 30 Sep 09:00". */
export function local(timestamp: string, timezone: string): string {
  const parts = new Intl.DateTimeFormat("en-US", {
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
