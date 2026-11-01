// What the side panel of background subagents (ui/chat/subagents/) shows of them: which work, which wait for the
// user and what for, and one's steps kept current from the `subagent_step` events that bring each as it starts and
// finishes.
import type { ApprovalRequest, ApprovalRequired, BackgroundStep, BackgroundSubagent } from "$lib/api/types";

/** Still at it: working, or waiting for the user's answer. */
export function working(subagent: BackgroundSubagent): boolean {
  return subagent.status === "running" || subagent.status === "waiting";
}

/** How many of them work, and how many of those wait for the user. */
export function counts(subagents: BackgroundSubagent[]): { working: number; waiting: number } {
  const busy = subagents.filter(working);
  return { working: busy.length, waiting: busy.filter((s) => s.status === "waiting").length };
}

/** The first line of its task, what its card is named by. */
export function taskTitle(task: string): string {
  return task.trim().split("\n", 1)[0];
}

/** What it waits for, as a run's approvals are shown (ApprovalModal). */
export function asked(subagent: BackgroundSubagent): ApprovalRequired[] {
  return (subagent.waiting ?? []).map((w) => ({
    type: "ApprovalRequired",
    interrupt_id: w.interrupt_id,
    request: w.request as ApprovalRequest,
  }));
}

/** Its steps with one an event brought: a new one added in its place, one that finished replacing itself. */
export function withStep(steps: BackgroundStep[], step: BackgroundStep): BackgroundStep[] {
  return [...steps.filter((s) => s.index !== step.index), step].sort((a, b) => a.index - b.index);
}
