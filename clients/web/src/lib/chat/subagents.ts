// What the side panel of background subagents (ui/chat/subagents/) and the page of them all (routes/subagents) show of
// them: which work, which wait for the user and what for, the conversation each works for, and one's steps kept
// current from the `subagent_step` events that bring each as it starts and finishes.
import type { ApprovalRequest, ApprovalRequired, BackgroundStep, BackgroundSubagent, Conversation } from "$lib/api/types";
import { t } from "$lib/i18n.svelte";

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

/** What one of those asks, in a line: an MCP tool's call as its approval is titled, anything else by its command. */
export function asks(request: ApprovalRequest): string {
  if (request.call) return t("chat.approveCall", { tool: request.call.tool, server: request.call.server });
  return String(request.command ?? request.message ?? request.reason ?? "");
}

/** Its steps with one an event brought: a new one added in its place, one that finished replacing itself. */
export function withStep(steps: BackgroundStep[], step: BackgroundStep): BackgroundStep[] {
  return [...steps.filter((s) => s.index !== step.index), step].sort((a, b) => a.index - b.index);
}

/** What its card says it's doing: what it waits for, its step in progress, or how it ended. */
export function doing(subagent: BackgroundSubagent): string {
  if (subagent.status === "waiting") return t("subagents.waitingForYou");
  if (subagent.status === "running") return subagent.step || t("subagents.thinking");
  return subagent.status === "done" ? t("subagents.answered") : subagent.result;
}

/** The title of the conversation one works for, among those listed; untitled while it has none. */
export function conversationTitle(threadId: string, conversations: Pick<Conversation, "thread_id" | "title">[]): string {
  return conversations.find((c) => c.thread_id === threadId)?.title || t("common.untitled");
}
