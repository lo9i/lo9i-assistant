---
name: scheduling-jobs
description: Scheduling a job: its timing, a task that runs unattended, approvals. For schedule_job and update_job.
---

A job runs with nobody watching, in a conversation of its own, and only while the assistant's service runs.

## Timing

Give exactly one of:

- `schedule`: a cron expression in the user's time zone. "0 9 * * *" is every day at 09:00, "30 8 * * 1-5" weekdays at 08:30, "0 */2 * * *" every two hours, "0 18 * * 0" Sundays at 18:00.
- `at`: one run at a local date and time, like "2026-09-30T14:05". Work it out from the current time in the turn header for requests like "in 5 minutes" or "tomorrow at noon". The job turns itself off after it runs.
- `on_new_mail`: run whenever new email arrives, given the new messages. For "tell me on Telegram when my bank writes", the task decides which messages matter and stays quiet about the rest.

`timezone` is only for a job in another time zone than the user's. A job due while the service wasn't running is skipped as missed after a few hours.

## Writing the task

- Write it for yourself with nothing of this conversation: say what to do, for whom, and where to deliver the result. "Run the skill news-digest and send it to the user on Telegram", "Send the user a Telegram message: stretch".
- To reach the user somewhere, the task says to use send_message on a chat channel; a run's reply on its own only goes to the apps' notifications and the Jobs page.
- Name the skill it runs or the tools it needs (a plugin's mcp__<server>__<tool>, send_email): the run starts with those loaded.
- A repeated task belongs in a skill (save_skill) the job runs, so it can be changed without rescheduling.
- A job can't ask the user questions or delegate to subagents; say in the task what to do when something's missing.

## Approvals

Actions that need approval (a dangerous command, an email to someone outside the allowlist) are sent to the user's connected chat channels to approve, and the run waits for the answer. With no channel connected, or no answer in time, they're denied and the run is marked as needing attention. Prefer tasks that need none.

## Changing jobs

schedule_job with an existing name replaces that job. update_job changes one's timing or task, or pauses and resumes it (`enabled`); list_jobs shows them, active, paused and done.
