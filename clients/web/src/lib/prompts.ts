// The system prompt texts the user edits (Settings → System prompt): what the editor shows for each, and what its
// state is. Drafts are kept by section, so switching between sections doesn't lose what was typed.
import type { PromptSection } from "./api/types";

export type PromptState = "unsaved" | "edited" | "built-in";

/** What the editor shows: the draft when the user typed one, else the text in use. */
export function draftOf(section: PromptSection, drafts: Record<string, string>): string {
  return drafts[section.name] ?? section.text;
}

/** Unsaved when the draft differs from the text in use; else whether that text is the user's edit. */
export function promptState(section: PromptSection, draft: string): PromptState {
  if (draft.trim() !== section.text) return "unsaved";
  return section.edited ? "edited" : "built-in";
}

/** Whether Save does anything: a draft that differs and isn't empty (the daemon refuses an empty text). */
export function canSave(section: PromptSection, draft: string): boolean {
  return draft.trim() !== "" && draft.trim() !== section.text;
}
