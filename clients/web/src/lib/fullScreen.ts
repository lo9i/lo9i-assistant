// Showing one card full screen (a Home card, a conversation's card or pane): its button shows it, pressing it again
// or Esc gives the page back.

/** What's full screen after the button of `id` is pressed: it, or nothing when it already was. */
export function toggled(current: string | null, id: string): string | null {
  return current === id ? null : id;
}

/** Whether a key press gives the page back: Esc, unless what has the focus took it (a reply stopped, a find bar
 * closed) or a dialog is open, whose Esc closes the dialog. */
export function restoresOnEscape(e: Pick<KeyboardEvent, "key" | "defaultPrevented">, doc: Pick<Document, "querySelector">): boolean {
  return e.key === "Escape" && !e.defaultPrevented && doc.querySelector('[role="dialog"]') === null;
}
