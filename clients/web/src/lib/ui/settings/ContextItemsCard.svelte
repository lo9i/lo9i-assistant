<script lang="ts">
  import { compact } from "$lib/conversationStats";
  import { itemsOf, percent } from "$lib/contextParts";
  import { formatNumber, t } from "$lib/i18n.svelte";
  import type { StartingContext } from "$lib/api/types";
  import SettingsCard from "../Card.svelte";

  // What the part picked in the ring lists (each skill, fact, profile section, tool definition), largest first, each
  // with its share of the part; the part's own heading and instructions as one more. Clicking an entry shows it whole.
  type Props = { context: StartingContext | undefined; selected: string; color: string };
  let { context, selected, color }: Props = $props();
  const part = $derived(context?.parts.find((p) => p.name === selected));
  const items = $derived(context ? itemsOf(context.parts, selected) : []);
  const ofContext = $derived(part && context?.tokens ? part.tokens / context.tokens : 0);
  let open = $state<number | null>(null);
  $effect(() => {
    void selected;
    open = null;
  });
</script>

<SettingsCard
  id="context-items"
  title={part?.name ?? t("contextParts.itemsTitle")}
  sub={part ? t("contextParts.itemsSub", { tokens: compact(part.tokens), percent: percent(ofContext) }) : undefined}
>
  {#snippet status()}
    {#if items.length}<span class="pill">{items.filter((i) => !i.frame).length}</span>{/if}
  {/snippet}
  {#if !part}
    <p class="text-meta">{t("common.loading")}</p>
  {:else if !items.length}
    <p class="text-meta">{t("contextParts.noItems")}</p>
  {:else}
    <ul class="items">
      {#each items as item, i (i)}
        {@const name = item.frame ? t("contextParts.frame") : item.name}
        <li>
          <button type="button" class:open={open === i} aria-expanded={open === i} onclick={() => (open = open === i ? null : i)}>
            <span class="row">
              <span class="name" class:frame={item.frame}>{name}</span>
              <span class="tokens" title={formatNumber(item.tokens)}>{compact(item.tokens)}</span>
              <span class="share">{percent(item.share)}</span>
            </span>
            <span class="bar"><span style="width: {Math.max(item.share * 100, 0.5)}%; background: {color}"></span></span>
            {#if item.detail}<span class="detail text-meta">{item.detail}</span>{/if}
          </button>
        </li>
      {/each}
    </ul>
  {/if}
</SettingsCard>

<style>
  .items {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 2px;
    max-height: 460px;
    overflow-y: auto;
  }
  .items button {
    width: 100%;
    display: flex;
    flex-direction: column;
    gap: 5px;
    padding: 7px 8px;
    border: none;
    border-radius: var(--radius-sm);
    background: none;
    color: var(--color-text-primary);
    font: inherit;
    font-size: var(--font-size-sm);
    text-align: left;
    cursor: pointer;
  }
  .items button:hover,
  .items button.open {
    background: var(--color-bg-hover-ghost);
  }
  .items button:focus-visible {
    outline: 1px solid var(--color-divider);
  }
  .row {
    display: grid;
    grid-template-columns: 1fr auto 3.5em;
    gap: 10px;
    align-items: baseline;
  }
  .name {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .name.frame {
    color: var(--color-text-muted);
    font-style: italic;
  }
  .tokens,
  .share {
    font-variant-numeric: tabular-nums;
    text-align: right;
  }
  .share {
    color: var(--color-text-muted);
  }
  .bar {
    display: block;
    height: 3px;
    border-radius: var(--radius-full);
    background: color-mix(in srgb, var(--color-text-primary) 6%, transparent);
    overflow: hidden;
  }
  .bar span {
    display: block;
    height: 100%;
    border-radius: var(--radius-full);
  }
  .detail {
    display: -webkit-box;
    -webkit-line-clamp: 2;
    line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
    white-space: pre-wrap;
  }
  .open .name {
    white-space: normal;
  }
  .open .detail {
    display: block;
  }
</style>
