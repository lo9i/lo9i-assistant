import type { KeptKeys } from "./api/types";

// What a removed plugin left kept (its keys, its private repository's token), waiting for the user to
// keep or delete it. Every page that removes a plugin hands its answer here; the app shell asks.
class KeptKeysQuestion {
  pending = $state<KeptKeys | null>(null);

  ask(kept: KeptKeys | null | undefined): void {
    if (kept) this.pending = kept;
  }
}

export const keptKeys = new KeptKeysQuestion();

/** What a kept entry is listed as in Settings: its plugin, or the repository whose token is left. */
export function keptName(kept: KeptKeys): string {
  return kept.plugin || `Token for ${kept.repository_name}`;
}

/** "HELLO_TOKEN, HELLO_USER and the token for me/private": what the question names. */
export function describeKept(kept: KeptKeys): string {
  const parts = [...kept.keys];
  if (kept.repository) parts.push(`the token for ${kept.repository_name}`);
  return parts.length > 1 ? `${parts.slice(0, -1).join(", ")} and ${parts[parts.length - 1]}` : parts[0];
}
