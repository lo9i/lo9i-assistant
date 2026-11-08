<script lang="ts">
  import type { StartingContext } from "$lib/api/types";
  import { contextShare } from "$lib/doctor";
  import { compact } from "$lib/conversationStats";
  import { arcs, percent, shade } from "$lib/contextParts";
  import { formatNumber, t } from "$lib/i18n.svelte";
  import SettingsCard from "../Card.svelte";

  // What a new conversation's context is made of, as a ring of its parts, largest first. Hovering one shows its
  // numbers in the middle; picking one (ContextBreakdown) shows what it lists in the card beside it.
  type Props = { context: StartingContext | undefined; error?: string; selected: string; onselect: (name: string) => void };
  let { context, error, selected, onselect }: Props = $props();
  const shown = $derived(context ? arcs(context.parts) : []);
  let hovered = $state<number | null>(null);
  const focus = $derived(hovered !== null ? shown[hovered] : undefined);

  const SIZE = 200;
  const RADIUS = 84;
  const CIRCLE = 2 * Math.PI * RADIUS;
  // The card's surface between two arcs, so neighbouring shades stay apart.
  const GAP = 2;

  function dash(length: number): string {
    const drawn = shown.length > 1 ? Math.max(length * CIRCLE - GAP, 0.75) : CIRCLE;
    return `${drawn} ${CIRCLE}`;
  }
</script>

<SettingsCard id="context-parts" title={t("contextParts.title")} sub={t("contextParts.sub")}>
  {#snippet status()}
    {#if context?.window}
      <span class="pill" class:pill--danger={context.too_large}>{t("contextParts.ofWindow", { share: contextShare(context) })}</span>
    {/if}
  {/snippet}
  {#if context === undefined}
    <p class="text-meta">{error ?? t("common.loading")}</p>
  {:else}
    {@const data = context}
    <div class="chart">
      <div class="ring">
        <!-- The legend beside it is the keyboard's way to the same numbers; the arcs answer the pointer. -->
        <svg viewBox="0 0 {SIZE} {SIZE}" role="img" aria-label={t("contextParts.ring")}>
          <circle class="track" cx={SIZE / 2} cy={SIZE / 2} r={RADIUS} />
          <g transform="rotate(-90 {SIZE / 2} {SIZE / 2})">
            {#each shown as arc, rank (arc.name)}
              <!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_static_element_interactions -->
              <circle
                class="arc"
                class:active={hovered === rank || (hovered === null && selected === arc.name)}
                class:dim={hovered !== null && hovered !== rank}
                cx={SIZE / 2}
                cy={SIZE / 2}
                r={RADIUS}
                stroke={shade(rank, shown.length)}
                stroke-dasharray={dash(arc.length)}
                stroke-dashoffset={-arc.start * CIRCLE}
                onpointerenter={() => (hovered = rank)}
                onpointerleave={() => (hovered = null)}
                onclick={() => onselect(arc.name)}
              />
            {/each}
          </g>
        </svg>
        <div class="centre" aria-hidden="true">
          {#if focus}
            <span class="micro-label name">{focus.name}</span>
            <strong>{compact(focus.tokens)}</strong>
            <span class="text-meta">{t("contextParts.ofTotal", { percent: percent(focus.share) })}</span>
          {:else}
            <span class="micro-label">{t("contextParts.total")}</span>
            <strong>{compact(data.tokens)}</strong>
            {#if data.window}<span class="text-meta">{t("contextParts.window", { window: compact(data.window) })}</span>{/if}
          {/if}
        </div>
      </div>
      <ul class="legend">
        {#each shown as arc, rank (arc.name)}
          <li>
            <button
              type="button"
              class:active={hovered === rank}
              class:selected={selected === arc.name}
              aria-pressed={selected === arc.name}
              onpointerenter={() => (hovered = rank)}
              onpointerleave={() => (hovered = null)}
              onfocus={() => (hovered = rank)}
              onblur={() => (hovered = null)}
              onclick={() => onselect(arc.name)}
            >
              <span class="swatch" style="background: {shade(rank, shown.length)}"></span>
              <span class="label">{arc.name}</span>
              <span class="tokens" title={formatNumber(arc.tokens)}>{compact(arc.tokens)}</span>
              <span class="share">{percent(arc.share)}</span>
            </button>
          </li>
        {/each}
      </ul>
    </div>
  {/if}
</SettingsCard>

<style>
  .chart {
    display: grid;
    grid-template-columns: 200px minmax(0, 1fr);
    gap: 28px;
    align-items: center;
  }
  .ring {
    position: relative;
    width: 200px;
    height: 200px;
  }
  svg {
    width: 100%;
    height: 100%;
    display: block;
    overflow: visible;
  }
  .track {
    fill: none;
    stroke: color-mix(in srgb, var(--color-text-primary) 5%, transparent);
    stroke-width: 16;
  }
  .arc {
    fill: none;
    stroke-width: 16;
    cursor: pointer;
    transition:
      stroke-width 120ms ease,
      opacity 120ms ease;
  }
  .arc.active {
    stroke-width: 22;
  }
  .arc.dim {
    opacity: 0.45;
  }
  .centre {
    position: absolute;
    inset: 36px;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 2px;
    text-align: center;
    pointer-events: none;
  }
  .centre strong {
    font-size: var(--font-size-xl);
    font-weight: 600;
    letter-spacing: -0.01em;
    font-variant-numeric: tabular-nums;
  }
  .name {
    max-width: 100%;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .legend {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 2px;
    min-width: 0;
  }
  .legend button {
    width: 100%;
    display: grid;
    grid-template-columns: 10px 1fr auto 3.5em;
    align-items: center;
    gap: 10px;
    padding: 5px 8px;
    border: none;
    border-radius: var(--radius-sm);
    background: none;
    color: var(--color-text-primary);
    font: inherit;
    font-size: var(--font-size-sm);
    text-align: left;
    cursor: pointer;
  }
  .legend button.active {
    background: var(--color-bg-hover-ghost);
  }
  .legend button.selected {
    background: color-mix(in srgb, var(--ring-strong) 14%, transparent);
  }
  .legend button:focus-visible {
    outline: 1px solid var(--color-divider);
  }
  .swatch {
    width: 10px;
    height: 10px;
    border-radius: 3px;
  }
  .label {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .tokens,
  .share {
    font-variant-numeric: tabular-nums;
    text-align: right;
  }
  .share {
    color: var(--color-text-muted);
  }
  @media (max-width: 520px) {
    .chart {
      grid-template-columns: 1fr;
      justify-items: center;
    }
    .legend {
      width: 100%;
    }
  }
</style>
