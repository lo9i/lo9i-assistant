<script lang="ts">
  import { compact } from "$lib/conversationStats";
  import { itemsOf, percent } from "$lib/contextParts";
  import { useDaemon } from "$lib/daemon.svelte";
  import { formatNumber, t } from "$lib/i18n.svelte";
  import type { StartingContext } from "$lib/api/types";
  import SettingsCard from "../Card.svelte";
  import Toggle from "../Toggle.svelte";

  // What the part picked in the ring lists (each skill, fact, profile section, tool definition), largest first, each
  // with its share of the model's whole window (its bar against the largest); the part's own heading and instructions as one more. Clicking an entry shows it whole.
  // Saved facts lists every fact, each with a switch for whether it's basic: only basic ones are in the prompt (and
  // counted), the others come into a turn when a message touches them.
  type Props = { context: StartingContext | undefined; selected: string; color: string };
  let { context, selected, color }: Props = $props();
  const { client, notices } = useDaemon();
  const part = $derived(context?.parts.find((p) => p.name === selected));
  const items = $derived(context ? itemsOf(context.parts, selected, context.window) : []);
  const ofWindow = $derived(part && context?.window ? part.tokens / context.window : 0);
  const hasFacts = $derived(items.some((i) => i.fact_id));
  let open = $state<number | null>(null);
  $effect(() => {
    void selected;
    open = null;
  });

  // The facts being changed; the `memory` event that follows measures the context again.
  let changing = $state<string[]>([]);

  async function setBasic(id: string, basic: boolean): Promise<void> {
    changing = [...changing, id];
    try {
      await client.memory.setFactBasic(id, basic);
    } catch (e) {
      notices.report(e);
    } finally {
      changing = changing.filter((c) => c !== id);
    }
  }
</script>

<SettingsCard
  id="context-items"
  title={part?.name ?? t("contextParts.itemsTitle")}
  sub={part ? t("contextParts.itemsSub", { tokens: compact(part.tokens), percent: percent(ofWindow) }) : undefined}
>
  {#snippet status()}
    {#if items.length}<span class="pill">{items.filter((i) => !i.frame).length}</span>{/if}
  {/snippet}
  {#if !part}
    <p class="text-meta">{t("common.loading")}</p>
  {:else if !items.length}
    <p class="text-meta">{t("contextParts.noItems")}</p>
  {:else}
    {#if hasFacts}<p class="text-meta hint">{t("contextParts.factsHint")}</p>{/if}
    <ul class="items">
      {#each items as item, i (i)}
        {@const name = item.frame ? t("contextParts.frame") : item.name}
        {@const counted = !item.fact_id || item.tokens > 0}
        <li class:fact={item.fact_id}>
          <button type="button" class:open={open === i} aria-expanded={open === i} onclick={() => (open = open === i ? null : i)}>
            <span class="row">
              <span class="name" class:frame={item.frame}>{name}</span>
              {#if counted}
                <span class="tokens" title={formatNumber(item.tokens)}>{compact(item.tokens)}</span>
                <span class="share">{percent(item.share)}</span>
              {:else}
                <span class="aside">{item.basic ? t("contextParts.pastBudget") : t("contextParts.whenRelevant")}</span>
              {/if}
            </span>
            {#if counted}
              <span class="bar"><span style="width: {Math.max(item.scale * 100, 0.5)}%; background: {color}"></span></span>
            {/if}
            {#if item.detail}<span class="detail text-meta">{item.detail}</span>{/if}
          </button>
          {#if item.fact_id}
            {@const id = item.fact_id}
            <span class="basic" title={t("contextParts.basicLabel")}>
              <Toggle
                checked={item.basic ?? false}
                label={t("contextParts.basicLabel")}
                disabled={changing.includes(id)}
                onchange={(on) => setBasic(id, on)}
              />
            </span>
          {/if}
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
  .hint {
    margin: 0 0 8px;
  }
  .items li.fact {
    display: grid;
    grid-template-columns: 1fr auto;
    gap: 8px;
    align-items: start;
  }
  .basic {
    padding-top: 6px;
  }
  .aside {
    grid-column: span 2;
    color: var(--color-text-muted);
    text-align: right;
    white-space: nowrap;
  }
  .items button {
    width: 100%;
    min-width: 0;
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
