// Assistant replies are Markdown. Rendered to HTML, then sanitized, since the text comes from a model.
import DOMPurify from "dompurify";
import { marked } from "marked";

marked.setOptions({ gfm: true, breaks: false });

export function markdown(text: string): string {
  return DOMPurify.sanitize(marked.parse(text, { async: false }));
}

/** Markdown a plugin wrote (a provider's steps), its links opening in a new tab so following one keeps the
 * dialog it's shown in. */
export function markdownLinkingOut(text: string): string {
  const shown = DOMPurify.sanitize(marked.parse(text, { async: false }), { RETURN_DOM_FRAGMENT: true });
  for (const link of shown.querySelectorAll("a")) {
    link.target = "_blank";
    link.rel = "noreferrer";
  }
  const holder = document.createElement("div");
  holder.append(shown);
  return holder.innerHTML;
}
