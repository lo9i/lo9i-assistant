<script lang="ts">
  import { compact } from "$lib/conversationStats";
  import { t } from "$lib/i18n.svelte";

  // How full a context is: `tokens` of `limit`, as segments filling up with the percentage or, where its status bar
  // has little room (a container named status-bar, StatusBar's), a ring; on hover, a bubble with `heading`, the figures
  // and `note`. A dash while it isn't known: no window, or no tokens yet. The conversation's (ContextFuel) and a
  // subagent's (SubagentStatus).
  type Props = { tokens: number; limit: number; heading: string; note: string };
  let { tokens, limit, heading, note }: Props = $props();

  const known = $derived(limit > 0 && tokens > 0);
  const ratio = $derived(known ? Math.min(1, tokens / limit) : 0);
  const SEGMENTS = 24;
  // The ring's radius, and the length of its circle, which its filled arc is a share of.
  const RADIUS = 6;
  const CIRCLE = 2 * Math.PI * RADIUS;
  const filled = $derived(Math.round(ratio * SEGMENTS));
  const percent = $derived(Math.round(ratio * 100));
  const figure = $derived(known ? `${percent}%` : "–");
  // The accent colour until half full, then fading to yellow at three quarters and to red when full.
  const YELLOW = "#e5b931";
  const RED = "#e5534b";
  const color = $derived(
    ratio <= 0.5
      ? "var(--color-accent)"
      : ratio <= 0.75
        ? `color-mix(in oklab, ${YELLOW} ${share(ratio, 0.5)}%, var(--color-accent))`
        : `color-mix(in oklab, ${RED} ${share(ratio, 0.75)}%, ${YELLOW})`,
  );
  const figures = $derived(known ? t("fuel.figures", { used: compact(tokens), limit: compact(limit) }) : t("fuel.unknown"));

  /** How far `ratio` is through the quarter that starts at `from`, as a percentage. */
  function share(ratio: number, from: number): number {
    return Math.round(((ratio - from) / 0.25) * 100);
  }
</script>

<span class="wrap">
  <span class="fuel" style="border-color: {color}" aria-label={known ? t("fuel.label", { percent }) : t("fuel.unknownLabel")}>
    {#each Array(SEGMENTS) as _, i (i)}
      <span class="seg" style="background: {color}; opacity: {i < filled ? 0.4 : 0.1}"></span>
    {/each}
    <span class="percent" style="color: {color}">{figure}</span>
  </span>
  <svg
    class="ring"
    viewBox="0 0 16 16"
    width="16"
    height="16"
    role="img"
    aria-label={known ? t("fuel.label", { percent }) : t("fuel.unknownLabel")}
  >
    <circle cx="8" cy="8" r={RADIUS} fill="none" stroke={color} stroke-width="2.5" opacity="0.2" />
    <circle
      cx="8"
      cy="8"
      r={RADIUS}
      fill="none"
      stroke={color}
      stroke-width="2.5"
      stroke-linecap="round"
      stroke-dasharray="{ratio * CIRCLE} {CIRCLE}"
      transform="rotate(-90 8 8)"
    />
  </svg>
  <span class="bubble" role="tooltip">
    <span class="head">{heading} <b style="color: {color}">{figure}</b></span>
    <span class="figs">{figures}</span>
    <span class="note">{note}</span>
  </span>
</span>

<style>
  .wrap {
    position: relative;
    display: inline-flex;
    align-items: center;
  }
  .bubble {
    position: absolute;
    bottom: calc(100% + 8px);
    right: 0;
    width: max-content;
    max-width: 260px;
    display: flex;
    flex-direction: column;
    gap: 2px;
    padding: 8px 12px;
    border: 1px solid var(--color-border);
    border-radius: 10px;
    background: var(--color-bg-page);
    box-shadow: var(--shadow-popover);
    color: var(--color-text-muted);
    font-size: 12px;
    line-height: 1.4;
    white-space: normal;
    opacity: 0;
    transform: translateY(4px);
    pointer-events: none;
    transition:
      opacity 0.12s ease,
      transform 0.12s ease;
    z-index: 50;
  }
  .wrap:hover .bubble {
    opacity: 1;
    transform: translateY(0);
  }
  .head {
    display: flex;
    justify-content: space-between;
    gap: 12px;
    color: var(--color-text-primary);
    font-weight: 600;
  }
  .figs {
    font-variant-numeric: tabular-nums;
  }
  .note {
    color: var(--color-text-faint);
  }
  .fuel {
    display: inline-flex;
    align-items: center;
    gap: 2px;
    height: 10px;
    padding: 2px 4px;
    border: 1px solid;
    border-radius: 6px;
    box-sizing: content-box;
    cursor: default;
  }
  .percent {
    margin-left: 4px;
    font-variant-numeric: tabular-nums;
  }
  .seg {
    width: 3px;
    height: 100%;
    border-radius: 2px;
  }
  .ring {
    display: none;
    cursor: default;
  }
  @container status-bar (max-width: 640px) {
    .fuel {
      display: none;
    }
    .ring {
      display: block;
    }
  }
</style>
