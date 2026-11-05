// The tab picked in each conversation's panel of coding tasks (ui/chat/tasks/), while the app is open: a new session
// picks itself, and the newest shows until the user picks another.
class TaskTabs {
  #picked = $state<Record<string, string>>({});

  get(threadId: string): string | undefined {
    return this.#picked[threadId];
  }

  pick(threadId: string, sessionId: string): void {
    this.#picked[threadId] = sessionId;
  }
}

export const taskTabs = new TaskTabs();
