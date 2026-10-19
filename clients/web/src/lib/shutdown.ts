// Restarting or stopping the daemon from the Host card (src/assistant/daemon/shutdown.py). Either waits for
// the runs in progress to end; the page reloads once the daemon is back.

export type Ending = "restart" | "stop";

export const CONFIRM: Record<Ending, { title: string; text: string; action: string }> = {
  restart: {
    title: "Restart the assistant?",
    text: "It stops and starts again once the runs in progress end. This page reloads when it's back.",
    action: "Restart",
  },
  stop: {
    title: "Stop the assistant?",
    text:
      "Jobs, chat channels and the apps stop working until it's started again on the computer it runs on " +
      "(opening the terminal app there starts it). It waits for the runs in progress to end.",
    action: "Stop",
  },
};

/** What the page says once the daemon has accepted the request, until it's back. */
export function endingText(ending: Ending, waitingForRuns: number): string {
  const when = waitingForRuns === 0 ? "now" : `once ${runs(waitingForRuns)}`;
  if (ending === "restart") return `The assistant restarts ${when}. This page reloads when it's back.`;
  return `The assistant stops ${when}. Start it again on the computer it runs on; this page reloads when it's back.`;
}

function runs(count: number): string {
  return count === 1 ? "the run in progress ends" : `the ${count} runs in progress end`;
}
