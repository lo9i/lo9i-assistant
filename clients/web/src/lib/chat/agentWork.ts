// Talking to the agent a conversation is handed to (/claude) while it works on the last message: what's typed
// goes to it between its steps (core/agent/handoffs.py).
import { ApiError } from "../api/errors";
import type { RunningTask } from "../api/types";
import { describe } from "../notices";

type Notices = { notify(text: string, level: "info" | "warning"): void };

/** What became of a message for the working agent: it has it ("taken", shown among its steps as it's sent), it can't
 * take it now ("later": between two tasks, just finished, or its plugin is older), so it waits in the conversation's
 * queue for the run to end, or it couldn't be sent ("failed"). */
export type Told = "taken" | "later" | "failed";

/** Runs a call to the working agent. When the call itself fails, says why as a warning. */
export async function tellAgent(call: () => Promise<void>, notices: Notices): Promise<Told> {
  try {
    await call();
    return "taken";
  } catch (error) {
    if (error instanceof ApiError && error.status === 409) return "later";
    notices.notify(describe(error), "warning");
    return "failed";
  }
}

type Box = { text: string; files: File[] };

/** Puts what the agent couldn't take back in the message box: the text unless something else was typed meanwhile,
 * the files before any attached since. */
export function putBack(box: Box, text: string, files: File[]): void {
  if (!box.text) box.text = text;
  if (files.length) box.files = [...files, ...box.files];
}

/** The coding agents' tasks running in `threadId`: the one of the agent it's handed to (`handedTo`, its name), which
 * the status bar shows with that agent's name, and the others, which it lists apart. */
export function workingIn(
  tasks: readonly RunningTask[],
  threadId: string,
  handedTo: string | null,
): { handed: RunningTask | null; others: RunningTask[] } {
  const here = tasks.filter((task) => task.thread_id === threadId);
  const handed = handedTo === null ? null : (here.find((task) => task.agent === handedTo) ?? null);
  return { handed, others: here.filter((task) => task !== handed) };
}
