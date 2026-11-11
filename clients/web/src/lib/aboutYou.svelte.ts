import type { AboutYou, AboutYouStatus, HelpTopic } from "./api/types";

// The About you step (core/memory/about_you.py): the app shell shows it once the app opens while the profile has no
// name, and Settings → About you opens it again.
class AboutYouStep {
  open = $state(false);
}

export const aboutYouStep = new AboutYouStep();

/** What the user can say they mainly want help with, in the order shown. */
export const HELP_TOPICS: HelpTopic[] = ["email", "calendar", "coding", "expenses", "media", "hosts"];

/** The form's answers to start from: what the profile holds, else nothing. */
export function startAnswers(status: AboutYouStatus | null): AboutYou {
  const answers = status?.answers;
  return {
    name: answers?.name ?? "",
    language: answers?.language ?? "",
    reply_length: answers?.reply_length ?? null,
    help_with: [...(answers?.help_with ?? [])],
    other_help: answers?.other_help ?? "",
    email: answers?.email ?? "",
  };
}

/** The answers as they're saved: text trimmed, topics in the order shown. */
export function savedAnswers(form: AboutYou): AboutYou {
  const picked = new Set(form.help_with ?? []);
  return {
    name: form.name.trim(),
    language: form.language.trim(),
    reply_length: form.reply_length ?? null,
    help_with: HELP_TOPICS.filter((topic) => picked.has(topic)),
    other_help: form.other_help.trim(),
    email: form.email.trim(),
  };
}
