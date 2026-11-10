// Assistant replies are Markdown. Rendered to HTML, then sanitized, since the text comes from a model.
import DOMPurify from "dompurify";
import { marked, type Token, type TokensList } from "marked";

marked.setOptions({ gfm: true, breaks: false });

/** A reply's parts in order: Markdown rendered and sanitized, or an interactive app's source (a ```html-app block),
 * which `Markdown.svelte` runs in a sandboxed frame (`htmlApp.ts`) and DOMPurify never sees. */
export type MarkdownPart = { kind: "html"; html: string } | { kind: "app"; source: string };

const APP_LANGUAGE = "html-app";

export function markdown(text: string): string {
  return DOMPurify.sanitize(marked.parse(text, { async: false }));
}

/** The reply split around its apps. An app's block counts only once its fence closes, so one still streaming shows
 * as code instead of starting again with each word; one inside a list or a quote stays code too. */
export function markdownParts(text: string): MarkdownPart[] {
  const tokens = marked.lexer(text);
  const parts: MarkdownPart[] = [];
  let run: Token[] = [];
  const flush = () => {
    if (run.length) parts.push({ kind: "html", html: rendered(run, tokens.links) });
    run = [];
  };
  for (const token of tokens) {
    if (!isApp(token)) {
      run.push(token);
      continue;
    }
    flush();
    parts.push({ kind: "app", source: token.text });
  }
  flush();
  return parts;
}

function rendered(run: Token[], links: TokensList["links"]): string {
  return DOMPurify.sanitize(marked.parser(Object.assign(run, { links }) as TokensList));
}

function isApp(token: Token): token is Token & { type: "code"; text: string } {
  return token.type === "code" && token.lang?.split(/\s/)[0] === APP_LANGUAGE && closed(token.raw);
}

/** Whether a fenced block's last line is a fence as long as its opening one, of the same character. */
function closed(raw: string): boolean {
  const lines = raw.trimEnd().split("\n");
  const fence = /^ {0,3}(`{3,}|~{3,})/.exec(lines[0])?.[1];
  if (!fence || lines.length < 2) return false;
  return new RegExp(`^ {0,3}${fence[0]}{${fence.length},}[ \\t]*$`).test(lines[lines.length - 1]);
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
