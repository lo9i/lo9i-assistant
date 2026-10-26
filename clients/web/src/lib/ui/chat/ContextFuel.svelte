<script lang="ts">
  import { compact } from "$lib/conversationStats";
  import { resource } from "$lib/daemon.svelte";

  // In the status bar: how full the conversation's context is. At the limit, older messages are summarized. While
  // the conversation is handed to an agent (/claude), the agent's context, as of its last answer.
  let { threadId }: { threadId: string } = $props();

  const stats = resource((c) => c.conversations.stats(threadId), ["run_finished", "handoffs"]);
  const shown = $derived(
    stats.data && !stats.error && stats.data.thread_id === threadId && stats.data.context_limit > 0 ? stats.data : null,
  );
  const ratio = $derived(shown ? Math.min(1, shown.context_tokens / shown.context_limit) : 0);
  const SEGMENTS = 24;
  const filled = $derived(Math.round(ratio * SEGMENTS));
  const percent = $derived(Math.round(ratio * 100));
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

  /** How far `ratio` is through the quarter that starts at `from`, as a percentage. */
  function share(ratio: number, from: number): number {
    return Math.round(((ratio - from) / 0.25) * 100);
  }
  const info = $derived.by(() => {
    if (!shown) return null;
    return {
      heading: shown.context_agent ? `${shown.context_agent}'s context` : "Context",
      figures: `${compact(shown.context_tokens)} / ${compact(shown.context_limit)} tokens`,
      note: shown.context_agent
        ? "As of its last answer. It compacts older messages as it nears full."
        : "Older messages are summarized when it's full.",
    };
  });
</script>

{#if shown}
  <span class="wrap">
    <span class="fuel" style="border-color: {color}" aria-label="Context {percent}%">
      {#each Array(SEGMENTS) as _, i (i)}
        <span class="seg" style="background: {color}; opacity: {i < filled ? 0.4 : 0.1}"></span>
      {/each}
      <span class="percent" style="color: {color}">{percent}%</span>
    </span>
    {#if info}
      <span class="bubble" role="tooltip">
        <span class="head">{info.heading} <b style="color: {color}">{percent}%</b></span>
        <span class="figs">{info.figures}</span>
        <span class="note">{info.note}</span>
      </span>
    {/if}
  </span>
{/if}

<style>
  .wrap {
    position: relative;
    display: inline-flex;
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
</style>
