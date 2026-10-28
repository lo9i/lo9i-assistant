<script lang="ts">
  import { resolve } from "$app/paths";
  import ArrowDown from "@lucide/svelte/icons/arrow-down";
  import ArrowUp from "@lucide/svelte/icons/arrow-up";
  import ExternalLink from "@lucide/svelte/icons/external-link";
  import Pencil from "@lucide/svelte/icons/pencil";
  import Trash from "@lucide/svelte/icons/trash-2";
  import type { HomeCard, PluginIcon as Icon } from "$lib/api/types";
  import { MAX_COLUMNS as MAX, SHOWN_ITEMS, cardColumns, itemWhen, linked, snappedColumns } from "$lib/home";
  import { pageLabel } from "$lib/pages";
  import PluginIcon from "../PluginIcon.svelte";

  type Props = {
    card: HomeCard;
    // The width saved for it (0 for automatic), the one last asked for while a save is on its way.
    columns: number;
    // The icon of the plugin it reads first; none when that isn't installed.
    icon?: Icon | null;
    // YYYY-MM-DD, to say when each item is.
    today: string;
    refreshing: boolean;
    first: boolean;
    last: boolean;
    onedit: () => void;
    ondelete: () => void;
    onmove: (by: -1 | 1) => void;
    onresize: (columns: number) => void;
  };
  let { card, columns, icon = null, today, refreshing, first, last, onedit, ondelete, onmove, onresize }: Props = $props();
  const result = $derived(card.result);
  const items = $derived(result?.items ?? []);
  // More shows the rest in place.
  let unfolded = $state(false);
  const shown = $derived(unfolded ? items : items.slice(0, SHOWN_ITEMS));
  const timed = $derived(items.some((item) => itemWhen(item, today)));

  let element = $state<HTMLElement>();
  // The columns it snaps to while its right edge is dragged; null when it isn't.
  let dragged = $state<number | null>(null);
  const settled = $derived(cardColumns({ columns }, items));
  const span = $derived(dragged ?? settled);

  // The page's columns as laid out now, which the card snaps to.
  function grid(): { column: number; gap: number; available: number } | null {
    const parent = element?.parentElement;
    if (!parent) return null;
    const style = getComputedStyle(parent);
    const tracks = style.gridTemplateColumns.split(" ");
    return { column: parseFloat(tracks[0]), gap: parseFloat(style.columnGap) || 0, available: tracks.length };
  }

  function startDrag(e: PointerEvent & { currentTarget: HTMLElement }): void {
    const page = grid();
    if (e.button !== 0 || !page) return;
    e.preventDefault();
    e.currentTarget.setPointerCapture(e.pointerId);
    dragged = Math.min(span, page.available);
  }

  function drag(e: PointerEvent): void {
    const page = grid();
    if (dragged === null || !page || !element) return;
    const width = e.clientX - element.getBoundingClientRect().left;
    dragged = snappedColumns(width, page.column, page.gap, page.available);
  }

  function endDrag(): void {
    if (dragged !== null) resize(dragged);
    dragged = null;
  }

  function resizeBy(e: KeyboardEvent): void {
    const by = { ArrowRight: 1, ArrowLeft: -1 }[e.key];
    const page = grid();
    if (!by || !page) return;
    e.preventDefault();
    resize(Math.max(1, Math.min(settled, page.available) + by));
  }

  function resize(to: number): void {
    const page = grid();
    if (page && to <= page.available && to !== Math.min(settled, page.available)) onresize(to);
  }
</script>

<section class="card surface--glass" data-span={span} bind:this={element} aria-label={card.section.title}>
  <header>
    <h2 class="text-heading title">
      {#if icon}<span class="plugin-icon"><PluginIcon {icon} size={18} /></span>{/if}{card.section.title}
    </h2>
    <div class="tools">
      <button class="btn btn--icon" title="Move up" aria-label="Move up" disabled={first} onclick={() => onmove(-1)}
        ><ArrowUp size={16} /></button
      >
      <button class="btn btn--icon" title="Move down" aria-label="Move down" disabled={last} onclick={() => onmove(1)}
        ><ArrowDown size={16} /></button
      >
      <button class="btn btn--icon" title="Edit" aria-label="Edit {card.section.title}" onclick={onedit}><Pencil size={16} /></button>
      <button class="btn btn--icon" title="Remove" aria-label="Remove {card.section.title}" onclick={ondelete}><Trash size={16} /></button>
      {#if result?.page}
        <a
          class="btn btn--icon"
          href={resolve("/pages/[name]", { name: result.page })}
          title="Open {pageLabel(result.page)}"
          aria-label="Open {pageLabel(result.page)}"><ExternalLink size={16} /></a
        >
      {/if}
    </div>
  </header>

  {#if !result}
    <p class="text-meta">{refreshing ? "Building…" : "Not built yet. Refresh to build it."}</p>
  {:else if result.status === "unavailable"}
    <p class="text-meta">{result.error} <a href={resolve("/plugins")}>Open Plugins</a></p>
  {:else}
    {#if result.status === "failed"}
      <p class="error-text small">Couldn't update it: {result.error}</p>
    {/if}
    {#if items.length}
      <ul class:stale={result.status === "failed"} class:timed>
        {#each shown as item, i (i)}
          {@const { subtitle, url } = linked(item)}
          <li>
            {#if timed}<span class="when">{itemWhen(item, today)}</span>{/if}
            <span class="what">
              {#if url}
                <a class="title" href={url} target="_blank" rel="noopener noreferrer">{item.title}</a>
              {:else}
                <span class="title">{item.title}</span>
              {/if}
              {#if subtitle}<span class="text-label">{subtitle}</span>{/if}
            </span>
          </li>
        {/each}
      </ul>
      {#if items.length > SHOWN_ITEMS}
        <button class="btn btn--ghost btn--sm more" onclick={() => (unfolded = !unfolded)}>
          {unfolded ? "Less" : `${items.length - SHOWN_ITEMS} more`}
        </button>
      {/if}
    {:else if result.status === "ok" && !result.note}
      <p class="text-meta">Nothing to show.</p>
    {/if}
    {#if result.note}<p class="text-meta">{result.note}</p>{/if}
  {/if}
  <!-- A focusable separator is a widget (ARIA's window splitter): dragged, or resized with its arrow keys. -->
  <!-- svelte-ignore a11y_no_noninteractive_tabindex, a11y_no_noninteractive_element_interactions -->
  <div
    class="resize"
    class:dragging={dragged !== null}
    role="separator"
    aria-orientation="vertical"
    aria-label="Width of {card.section.title}, in columns"
    aria-valuemin={1}
    aria-valuemax={MAX}
    aria-valuenow={span}
    title="Drag to make it wider or narrower"
    tabindex="0"
    onpointerdown={startDrag}
    onpointermove={drag}
    onpointerup={endDrag}
    onpointercancel={() => (dragged = null)}
    onkeydown={resizeBy}
  ></div>
</section>

<style>
  h2.title {
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .plugin-icon {
    display: inline-flex;
    color: var(--color-text-muted);
  }
  /* A card spans the columns it was given (or two when it's busy) as far as the page has them: Home's columns are at
   least 320px with 16px between them, so two from 656px, three from 992px, four from 1328px. On a narrow page
   every card is one column, and there's nothing to resize. */
  @container home-grid (min-width: 656px) {
    .card:not([data-span="1"]) {
      grid-column: span 2;
    }
    .resize {
      display: block;
    }
  }
  @container home-grid (min-width: 992px) {
    .card[data-span="3"],
    .card[data-span="4"] {
      grid-column: span 3;
    }
  }
  @container home-grid (min-width: 1328px) {
    .card[data-span="4"] {
      grid-column: span 4;
    }
  }
  .card {
    position: relative;
    display: flex;
    flex-direction: column;
    gap: 12px;
    padding: 20px;
    min-width: 0;
  }
  header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
  }
  .tools {
    display: flex;
    gap: 2px;
    --btn-icon-size: 28px;
  }
  /* The right edge, dragged to snap the card to more or fewer columns. */
  .resize {
    display: none;
    position: absolute;
    top: 16px;
    bottom: 16px;
    right: 0;
    width: 10px;
    cursor: ew-resize;
    touch-action: none;
  }
  .resize::after {
    content: "";
    position: absolute;
    top: 50%;
    right: 3px;
    width: 4px;
    height: 32px;
    transform: translateY(-50%);
    border-radius: 2px;
    background: var(--color-border);
    opacity: 0;
    transition: opacity 0.12s ease;
  }
  .card:hover .resize::after,
  .resize:focus-visible::after,
  .resize.dragging::after {
    opacity: 1;
  }
  .resize.dragging::after,
  .resize:focus-visible::after {
    background: var(--color-accent);
  }
  /* The tools show on hover or focus, so the cards read as content. */
  @media (hover: hover) {
    .tools > :not(a) {
      opacity: 0;
      transition: opacity 0.12s ease;
    }
    .card:hover .tools > *,
    .card:focus-within .tools > * {
      opacity: 1;
    }
  }
  /* One column of times as wide as the longest ("Tomorrow 21:00"), so the titles line up; none when no item has
   a time. */
  ul {
    list-style: none;
    margin: 0;
    padding: 0;
    display: grid;
    grid-template-columns: 1fr;
    column-gap: 16px;
  }
  ul.timed {
    grid-template-columns: max-content 1fr;
  }
  ul.stale {
    opacity: 0.6;
  }
  li {
    display: grid;
    grid-column: 1 / -1;
    grid-template-columns: subgrid;
    padding: 8px 0;
    border-top: 1px solid color-mix(in srgb, var(--color-border) 55%, transparent);
  }
  li:first-child {
    border-top: 0;
    padding-top: 0;
  }
  .when {
    white-space: nowrap;
    font-size: var(--font-size-sm);
    font-variant-numeric: tabular-nums;
    color: var(--color-text-muted);
  }
  .what {
    display: flex;
    flex-direction: column;
    gap: 2px;
    min-width: 0;
    overflow-wrap: anywhere;
  }
  .title {
    font-weight: 500;
  }
  a.title {
    align-self: flex-start;
    color: inherit;
    text-decoration: none;
  }
  a.title:hover,
  a.title:focus-visible {
    text-decoration: underline;
  }
  .more {
    align-self: flex-start;
  }
  p {
    margin: 0;
  }
  .small {
    font-size: var(--font-size-sm);
  }
</style>
