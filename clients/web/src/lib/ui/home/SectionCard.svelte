<script lang="ts">
  import { resolve } from "$app/paths";
  import ArrowDown from "@lucide/svelte/icons/arrow-down";
  import ArrowUp from "@lucide/svelte/icons/arrow-up";
  import ExternalLink from "@lucide/svelte/icons/external-link";
  import Pencil from "@lucide/svelte/icons/pencil";
  import Trash from "@lucide/svelte/icons/trash-2";
  import type { HomeCard, PluginIcon as Icon } from "$lib/api/types";
  import { SHOWN_ITEMS, isWide, itemWhen, linked } from "$lib/home";
  import { pageLabel } from "$lib/pages";
  import PluginIcon from "../PluginIcon.svelte";

  type Props = {
    card: HomeCard;
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
  };
  let { card, icon = null, today, refreshing, first, last, onedit, ondelete, onmove }: Props = $props();
  const result = $derived(card.result);
  const items = $derived(result?.items ?? []);
  // More shows the rest in place.
  let unfolded = $state(false);
  const shown = $derived(unfolded ? items : items.slice(0, SHOWN_ITEMS));
  const timed = $derived(items.some((item) => itemWhen(item, today)));
</script>

<section class="card surface--glass" class:wide={isWide(items)} aria-label={card.section.title}>
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
  /* A busy card takes two columns once the page has two; on a narrow one every card is one column. */
  @container home-grid (min-width: 656px) {
    .card.wide {
      grid-column: span 2;
    }
  }
  .card {
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
