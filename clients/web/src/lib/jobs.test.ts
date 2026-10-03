import { describe, expect, it } from "vitest";
import type { Job } from "./api/types";
import { every, local, summary } from "./jobs";

const job = (change: Partial<Job>): Job => ({
  name: "news",
  user_id: "owner",
  schedule: "0 9 * * *",
  timezone: "Europe/Madrid",
  task: "Send me the news",
  next_run_at: "2026-09-30T07:00:00+00:00",
  enabled: true,
  runs: [],
  one_time: false,
  on_new_mail: false,
  ...change,
});

describe("job text", () => {
  it("shows times in the job's time zone", () => {
    expect(local("2026-09-30T07:00:00+00:00", "Europe/Madrid")).toBe("Wed 30 Sep 09:00");
  });

  it("summarizes repeating, paused and finished jobs", () => {
    expect(summary(job({}))).toBe("0 9 * * * (Europe/Madrid) · next Wed 30 Sep 09:00");
    expect(summary(job({ enabled: false }))).toBe("0 9 * * * (Europe/Madrid) · paused");
    const done = job({ one_time: true, enabled: false, runs: [{ at: "2026-09-30T07:00:00+00:00", status: "ok", summary: "", thread_id: "" }] });
    expect(summary(done)).toBe("once at Wed 30 Sep 09:00 · done");
  });
});

describe("every", () => {
  it("says how often a job runs", () => {
    expect(every(job({}))).toBe("Every day at 09:00");
    expect(every(job({ schedule: "0 8 * * 1-5" }))).toBe("At 08:00, Monday through Friday");
    expect(every(job({ schedule: "*/15 * * * *" }))).toBe("Every 15 minutes");
    expect(every(job({ one_time: true, schedule: "" }))).toBe("Once, on Wed 30 Sep 09:00");
  });

  it("describes jobs that run on new mail, with no next run", () => {
    const mail = job({ on_new_mail: true, schedule: "", next_run_at: "" });
    expect(every(mail)).toBe("On each new email");
    expect(summary(mail)).toBe("on each new email · waiting for mail");
    expect(summary({ ...mail, enabled: false })).toBe("on each new email · paused");
  });
});
