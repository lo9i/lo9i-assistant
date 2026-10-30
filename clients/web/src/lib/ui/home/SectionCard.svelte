<script lang="ts">
  import { resolve } from "$app/paths";
  import ArrowDown from "@lucide/svelte/icons/arrow-down";
  import ArrowUp from "@lucide/svelte/icons/arrow-up";
  import ExternalLink from "@lucide/svelte/icons/external-link";
  import GripVertical from "@lucide/svelte/icons/grip-vertical";
  import Maximize2 from "@lucide/svelte/icons/maximize-2";
  import Minimize2 from "@lucide/svelte/icons/minimize-2";
  import Pencil from "@lucide/svelte/icons/pencil";
  import Trash from "@lucide/svelte/icons/trash-2";
  import type { Snippet } from "svelte";
  import type { HomeCard, PluginIcon as Icon } from "$lib/api/types";
  import { MAX_COLUMNS as MAX, cardColumns, itemWhen, linked, snappedColumns } from "$lib/home";
  import { t } from "$lib/i18n.svelte";
  import { pageHref, pageLabel } from "$lib/pages";
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
    /** Shown full screen: over the page, without the tools that place it. */
    maximized?: boolean;
    onmaximize: () => void;
    /** Dragging its header moves it; a drop on it says where by `drop`. */
    ondragstart?: (e: DragEvent) => void;
    ondragover?: (e: DragEvent) => void;
    ondrop?: (e: DragEvent) => void;
    /** Where a card dragged over it would go: before it, after it, or nowhere. */
    drop?: "before" | "after" | null;
    /** What it shows instead of its result's items (the Conversations card, drawn live). */
    children?: Snippet;
  };
  let {
    card,
    columns,
    icon = null,
    today,
    refreshing,
    first,
    last,
    onedit,
    ondelete,
    onmove,
    onresize,
    maximized = false,
    onmaximize,
    ondragstart,
    ondragover,
    ondrop,
    drop = null,
    children,
  }: Props = $props();
  const result = $derived(card.result);
  const items = $derived(result?.items ?? []);
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

<section
  class="card surface--glass"
  class:maximized
  class:drop-before={drop === "before"}
  class:drop-after={drop === "after"}
  data-span={span}
  bind:this={element}
  aria-label={card.section.title}
  {ondragover}
  {ondrop}
>
  <!-- Dragging is the mouse's way to move it; its arrows do the same from the keyboard and on a phone. -->
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <header draggable={!maximized && ondragstart !== undefined} {ondragstart} class:movable={!maximized && ondragstart}>
    <h2 class="text-heading title">
      {#if !maximized && ondragstart}<span class="grip" aria-hidden="true" title={t("home.dragToMove")}><GripVertical size={14} /></span
        >{/if}
      {#if icon}<span class="plugin-icon"><PluginIcon {icon} size={18} /></span>{/if}{card.section.title}
    </h2>
    <div class="tools">
      {#if !maximized}
        <button class="btn btn--icon" title={t("home.moveUp")} aria-label={t("home.moveUp")} disabled={first} onclick={() => onmove(-1)}
          ><ArrowUp size={16} /></button
        >
        <button class="btn btn--icon" title={t("home.moveDown")} aria-label={t("home.moveDown")} disabled={last} onclick={() => onmove(1)}
          ><ArrowDown size={16} /></button
        >
      {/if}
      <button class="btn btn--icon" title={t("common.edit")} aria-label={t("home.editName", { title: card.section.title })} onclick={onedit}
        ><Pencil size={16} /></button
      >
      <button
        class="btn btn--icon"
        title={t("common.remove")}
        aria-label={t("home.removeName", { title: card.section.title })}
        onclick={ondelete}><Trash size={16} /></button
      >
      {#if result?.page}
        <a
          class="btn btn--icon"
          href={resolve("/pages/[name]", { name: result.page })}
          title={t("home.openPage", { page: pageLabel(result.page) })}
          aria-label={t("home.openPage", { page: pageLabel(result.page) })}><ExternalLink size={16} /></a
        >
      {/if}
      <button
        class="btn btn--icon full"
        title={maximized ? t("home.restore") : t("home.maximize")}
        aria-label={maximized ? t("home.restore") : t("home.maximize")}
        aria-pressed={maximized}
        onclick={onmaximize}
        >{#if maximized}<Minimize2 size={16} />{:else}<Maximize2 size={16} />{/if}</button
      >
    </div>
  </header>

  {#if children}
    {@render children()}
  {:else if !result}
    <p class="text-meta">{refreshing ? t("home.building") : t("home.notBuilt")}</p>
  {:else if result.status === "unavailable"}
    <p class="text-meta">{result.error} <a href={resolve("/plugins")}>{t("home.openPlugins")}</a></p>
  {:else}
    {#if result.status === "failed"}
      <p class="error-text small">{t("home.couldntUpdate", { error: result.error })}</p>
    {/if}
    {#if items.length}
      <ul class:stale={result.status === "failed"} class:timed>
        {#each items as item, i (i)}
          {@const { subtitle, url } = linked(item)}
          <li>
            {#if timed}<span class="when">{itemWhen(item, today)}</span>{/if}
            <span class="what">
              {#if url}
                <a class="title" href={url} target="_blank" rel="noopener noreferrer">{item.title}</a>
              {:else if item.page_path && result.page}
                <!-- Its place on the plugin's page, in the app. -->
                <a class="title" href={pageHref(resolve("/pages/[name]", { name: result.page }), item.page_path)}>{item.title}</a>
              {:else}
                <span class="title">{item.title}</span>
              {/if}
              {#if subtitle}<span class="text-label">{subtitle}</span>{/if}
            </span>
          </li>
        {/each}
      </ul>
    {:else if result.status === "ok" && !result.note}
      <p class="text-meta">{t("home.nothing")}</p>
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
    aria-label={t("home.widthOf", { title: card.section.title })}
    aria-valuemin={1}
    aria-valuemax={MAX}
    aria-valuenow={span}
    title={t("home.dragHint")}
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
  /* Over the whole app, sidebar included; dialogs still open above it. */
  .card.maximized {
    position: fixed;
    inset: 12px;
    z-index: 60;
    overflow-y: auto;
    background: var(--surface-modal-bg);
  }
  .card.maximized :global(ul) {
    max-height: none;
  }
  /* Full screen it has nothing to snap to. */
  .card.maximized .resize {
    display: none;
  }
  header.movable {
    cursor: grab;
  }
  header.movable:active {
    cursor: grabbing;
  }
  .grip {
    display: inline-flex;
    color: var(--color-text-faint);
  }
  /* Where a card dragged over it goes: a bar before or after it. */
  .card.drop-before::before,
  .card.drop-after::after {
    content: "";
    position: absolute;
    top: 0;
    bottom: 0;
    width: 3px;
    border-radius: 2px;
    background: color-mix(in srgb, var(--glow) 90%, transparent);
  }
  .card.drop-before::before {
    left: -10px;
  }
  .card.drop-after::after {
    right: -10px;
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
    .card:focus-within .tools > *,
    .card.maximized .tools > * {
      opacity: 1;
    }
  }
  /* One column of times as wide as the longest ("Tomorrow 21:00"), so the titles line up; none when no item has
   a time. A long list scrolls past about five items, so its card doesn't tower over the others. */
  ul {
    list-style: none;
    margin: 0;
    padding: 0 4px 0 0;
    max-height: 18rem;
    overflow-y: auto;
    overscroll-behavior: contain;
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
  p {
    margin: 0;
  }
  .small {
    font-size: var(--font-size-sm);
  }
</style>
