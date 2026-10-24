<script lang="ts">
  import { resolve } from "$app/paths";
  import ArrowDown from "@lucide/svelte/icons/arrow-down";
  import ArrowUp from "@lucide/svelte/icons/arrow-up";
  import ExternalLink from "@lucide/svelte/icons/external-link";
  import Pencil from "@lucide/svelte/icons/pencil";
  import Trash from "@lucide/svelte/icons/trash-2";
  import type { HomeCard, PluginIcon as Icon } from "$lib/api/types";
  import { itemWhen } from "$lib/home";
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
</script>

<section class="card surface--glass" aria-label={card.section.title}>
  <header>
    <h2 class="text-heading title">
      {#if icon}<span class="plugin-icon"><PluginIcon {icon} size={18} /></span>{/if}{card.section.title}
    </h2>
    <div class="tools">
      {#if result?.page}
        <a
          class="btn btn--icon"
          href={resolve("/pages/[name]", { name: result.page })}
          title="Open {pageLabel(result.page)}"
          aria-label="Open {pageLabel(result.page)}"><ExternalLink size={16} /></a
        >
      {/if}
      <button class="btn btn--icon" title="Move up" aria-label="Move up" disabled={first} onclick={() => onmove(-1)}
        ><ArrowUp size={16} /></button
      >
      <button class="btn btn--icon" title="Move down" aria-label="Move down" disabled={last} onclick={() => onmove(1)}
        ><ArrowDown size={16} /></button
      >
      <button class="btn btn--icon" title="Edit" aria-label="Edit {card.section.title}" onclick={onedit}><Pencil size={16} /></button>
      <button class="btn btn--icon" title="Remove" aria-label="Remove {card.section.title}" onclick={ondelete}><Trash size={16} /></button>
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
    {#if result.items.length}
      <ul class:stale={result.status === "failed"}>
        {#each result.items as item, i (i)}
          <li>
            <span class="when">{itemWhen(item, today)}</span>
            <span class="what">
              <span class="title">{item.title}</span>
              {#if item.subtitle}<span class="text-label">{item.subtitle}</span>{/if}
            </span>
          </li>
        {/each}
      </ul>
    {:else if result.status === "ok" && !result.note}
      <p class="text-meta">Nothing to show.</p>
    {/if}
    {#if result.note}<p class="text-meta">{result.note}</p>{/if}
  {/if}
</section>

<style>
  .title {
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .plugin-icon {
    display: inline-flex;
    color: var(--color-text-muted);
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
  /* One column of times as wide as the longest ("Tomorrow 21:00"), so the titles line up. */
  ul {
    list-style: none;
    margin: 0;
    padding: 0;
    display: grid;
    grid-template-columns: max-content 1fr;
    column-gap: 16px;
  }
  ul.stale {
    opacity: 0.6;
  }
  li {
    display: grid;
    grid-column: span 2;
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
  p {
    margin: 0;
  }
  .small {
    font-size: var(--font-size-sm);
  }
</style>
