// Talking to the agent a conversation is handed to (/claude) while it works on the last message: what's typed
// goes to it between its steps (core/agent/handoffs.py).
import { describe } from "../notices";

type Notices = { notify(text: string, level: "info" | "warning"): void };

/** Runs a call to the working agent. When it can't take it (it just finished, or its plugin is older), says why
 * as a warning and returns false. */
export async function tellAgent(call: () => Promise<void>, notices: Notices): Promise<boolean> {
  try {
    await call();
    return true;
  } catch (error) {
    notices.notify(describe(error), "warning");
    return false;
  }
}

type Box = { text: string; files: File[] };

/** Puts what the agent couldn't take back in the message box: the text unless something else was typed meanwhile,
 * the files before any attached since. */
export function putBack(box: Box, text: string, files: File[]): void {
  if (!box.text) box.text = text;
  if (files.length) box.files = [...files, ...box.files];
}
