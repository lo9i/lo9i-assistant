// Assistant replies are Markdown. Rendered to HTML, then sanitized, since the text comes from a model.
import DOMPurify from "dompurify";
import { marked } from "marked";

marked.setOptions({ gfm: true, breaks: false });

export function markdown(text: string): string {
  return DOMPurify.sanitize(marked.parse(text, { async: false }));
}
