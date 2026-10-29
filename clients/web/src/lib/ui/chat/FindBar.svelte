<script lang="ts">
  import ChevronDown from "@lucide/svelte/icons/chevron-down";
  import ChevronUp from "@lucide/svelte/icons/chevron-up";
  import X from "@lucide/svelte/icons/x";
  import { onDestroy, untrack } from "svelte";
  import { counter, locate, nearest, step } from "$lib/chat/find";
  import { t } from "$lib/i18n.svelte";

  type Props = {
    /** What scrolls the messages; their text to search is in its `[data-findable]` elements. */
    root: HTMLElement | undefined;
    /** The messages shown: when they change (a reply streaming in), the matches are found again. */
    content: unknown;
    onclose: () => void;
  };
  let { root, content, onclose }: Props = $props();

  // Highlights are named for the whole page; their colours are in app.css.
  const MATCHES = "find-match";
  const CURRENT = "find-current";
  // How far down the messages' top the bar and the copy of the user's message under it cover.
  const HIDDEN_TOP = 120;
  const highlights = typeof CSS !== "undefined" && "highlights" in CSS ? CSS.highlights : null;

  let input = $state<HTMLInputElement>();
  let query = $state("");
  let matches = $state.raw<Range[]>([]);
  let current = $state(-1);
  // The query the matches were last found for: a new one starts at the match nearest the reader.
  let searched = "";

  /** Focuses the box with its text selected, as pressing Cmd+F again does. */
  export function focus(): void {
    input?.focus();
    input?.select();
  }

  $effect(() => {
    void content;
    const el = root;
    const text = query;
    untrack(() => find(el, text));
  });
  $effect(() => show(matches, current));
  onDestroy(() => {
    highlights?.delete(MATCHES);
    highlights?.delete(CURRENT);
  });

  function find(el: HTMLElement | undefined, text: string): void {
    matches = el ? ranges(el, text) : [];
    if (text !== searched) {
      searched = text;
      current = el ? nearest(matches.map(topOf), el.getBoundingClientRect().top) : -1;
      reveal();
    } else {
      current = Math.min(current, matches.length - 1);
      if (current === -1 && matches.length) current = 0;
    }
  }

  /** Each match of `text` in `el`'s messages, in the order they read. */
  function ranges(el: HTMLElement, text: string): Range[] {
    if (!text) return [];
    return [...el.querySelectorAll<HTMLElement>("[data-findable]")].flatMap((block) => {
      const nodes = textNodes(block);
      return locate(
        nodes.map((n) => n.data),
        text,
      ).map(({ start, end }) => {
        const range = document.createRange();
        range.setStart(nodes[start[0]], start[1]);
        range.setEnd(nodes[end[0]], end[1]);
        return range;
      });
    });
  }

  function textNodes(block: HTMLElement): Text[] {
    const walker = document.createTreeWalker(block, NodeFilter.SHOW_TEXT);
    const nodes: Text[] = [];
    while (walker.nextNode()) nodes.push(walker.currentNode as Text);
    return nodes;
  }

  /** Where a match sits; one in a collapsed section (a thought, a task) isn't drawn, so its section's. */
  function topOf(range: Range): number {
    const closed = range.startContainer.parentElement?.closest("details:not([open])");
    return (closed ?? range).getBoundingClientRect().top;
  }

  function show(all: Range[], at: number): void {
    if (!highlights) return;
    highlights.set(MATCHES, new Highlight(...all));
    const strong = new Highlight(...(at >= 0 && all[at] ? [all[at]] : []));
    // Drawn over the match highlight it overlaps.
    strong.priority = 1;
    highlights.set(CURRENT, strong);
  }

  function go(direction: 1 | -1): void {
    current = step(current, matches.length, direction);
    reveal();
  }

  /** Opens the sections the current match is in and, when it's out of view, scrolls it to the middle of the
   * messages. */
  function reveal(): void {
    const range = matches[current];
    if (!range || !root) return;
    for (let el = range.startContainer.parentElement?.closest("details"); el; el = el.parentElement?.closest("details")) {
      el.open = true;
    }
    const box = root.getBoundingClientRect();
    const rect = range.getBoundingClientRect();
    // Under the find bar and the pinned message at the top counts as out of view.
    if (rect.top >= box.top + HIDDEN_TOP && rect.bottom <= box.bottom) return;
    root.scrollBy({ top: rect.top - box.top - box.height / 2 + rect.height / 2, behavior: "smooth" });
  }

  function keydown(e: KeyboardEvent): void {
    if (e.key === "Enter") {
      e.preventDefault();
      go(e.shiftKey ? -1 : 1);
    } else if (e.key === "Escape") {
      e.preventDefault();
      onclose();
    }
  }
</script>

<div class="find" role="search">
  <input
    bind:this={input}
    bind:value={query}
    onkeydown={keydown}
    placeholder={t("find.placeholder")}
    aria-label={t("find.placeholder")}
    spellcheck="false"
  />
  <span class="count" aria-live="polite">{counter(current, matches.length, query)}</span>
  <button aria-label={t("find.previous")} title={t("find.previousHint")} disabled={matches.length === 0} onclick={() => go(-1)}>
    <ChevronUp size={16} />
  </button>
  <button aria-label={t("find.next")} title={t("find.nextHint")} disabled={matches.length === 0} onclick={() => go(1)}>
    <ChevronDown size={16} />
  </button>
  <button aria-label={t("common.close")} title={t("find.closeHint")} onclick={onclose}><X size={16} /></button>
</div>

<style>
  .find {
    position: absolute;
    top: 8px;
    right: 16px;
    z-index: 2;
    display: flex;
    align-items: center;
    gap: 2px;
    padding: 4px 4px 4px 12px;
    border: 1px solid var(--color-border);
    border-radius: var(--radius-sm);
    /* Solid, so the messages scrolling under it don't show through; the theme's teal-gray. */
    background: color-mix(in srgb, var(--glow) 22%, var(--color-bg-page));
    box-shadow: var(--shadow-popover);
  }
  .find:focus-within {
    border-color: color-mix(in srgb, var(--glow) 70%, transparent);
  }
  input {
    width: min(220px, 40vw);
    border: 0;
    outline: none;
    background: none;
    padding: 4px 0;
    color: var(--color-text-primary);
    font-size: var(--font-size-sm);
  }
  .count {
    min-width: 64px;
    padding: 0 6px;
    color: var(--color-text-muted);
    font-size: var(--font-size-xs);
    text-align: right;
    white-space: nowrap;
    font-variant-numeric: tabular-nums;
  }
  button {
    display: grid;
    place-items: center;
    width: 26px;
    height: 26px;
    border: none;
    border-radius: var(--radius-sm);
    background: transparent;
    color: var(--color-text-muted);
    cursor: pointer;
  }
  button:hover:not(:disabled) {
    background: var(--color-bg-hover-ghost);
    color: var(--color-text-primary);
  }
  button:disabled {
    opacity: 0.4;
    cursor: default;
  }
</style>
