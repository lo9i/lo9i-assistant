<script lang="ts">
  import Coins from "@lucide/svelte/icons/coins";
  import Mail from "@lucide/svelte/icons/mail";
  import Wrench from "@lucide/svelte/icons/wrench";
  import { statsDetail, statsFigures, statsLine } from "$lib/conversationStats";
  import { resource } from "$lib/daemon.svelte";

  // In the status bar: how long the conversation is and what it took, with its figures in a card on hover, grouped
  // under a title each; where the bar has little room (StatusBar's container), icons stand for the words. Loaded
  // again when the conversation changes and when a reply ends; shown from the start (all zeros), hidden only when it
  // can't be loaded.
  let { threadId }: { threadId: string } = $props();

  const stats = resource((c) => c.conversations.stats(threadId), ["run_finished"]);

  // The last conversation's stats stay until this one's arrive; they aren't shown meanwhile.
  const shown = $derived(stats.data && !stats.error && stats.data.thread_id === threadId ? stats.data : null);
</script>

{#if shown}
  {@const figures = statsFigures(shown)}
  <span class="wrap">
    <span class="stats">
      <span class="words">{statsLine(shown)}</span>
      <span class="icons" aria-label={statsLine(shown)}>
        <span><Mail size={12} aria-hidden="true" />{figures.messages}</span>
        <span><Coins size={12} aria-hidden="true" />{figures.tokens}</span>
        <span><Wrench size={12} aria-hidden="true" />{figures.tools}</span>
      </span>
    </span>
    <span class="bubble" role="tooltip">
      {#each statsDetail(shown) as group (group.title)}
        <span class="title">{group.title}</span>
        {#each group.rows as row (row.label)}
          <span class="label">{row.label}</span>
          <span class="value"
            >{row.value}{#if row.note}<span class="note">{row.note}</span>{/if}</span
          >
        {/each}
      {/each}
    </span>
  </span>
{/if}

<style>
  /* The first to give way when the status bar runs short; the card has it all. */
  .wrap {
    position: relative;
    display: inline-flex;
    flex: 0 100 auto;
    min-width: 0;
  }
  .stats {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    cursor: default;
    font-variant-numeric: tabular-nums;
  }
  .icons {
    display: none;
    align-items: center;
    gap: 10px;
  }
  .icons > span {
    display: inline-flex;
    align-items: center;
    gap: 3px;
  }
  /* As ContextFuel's: a card above the line, in a grid of labels and their values. */
  .bubble {
    position: absolute;
    bottom: calc(100% + 8px);
    left: 0;
    display: grid;
    grid-template-columns: auto auto;
    column-gap: 20px;
    row-gap: 2px;
    width: max-content;
    padding: 10px 12px;
    border: 1px solid var(--color-border);
    border-radius: 10px;
    background: var(--color-bg-page);
    box-shadow: var(--shadow-popover);
    color: var(--color-text-muted);
    font-size: 12px;
    line-height: 1.4;
    white-space: nowrap;
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
  .title {
    grid-column: 1 / -1;
    margin-top: 8px;
    color: var(--color-text-primary);
    font-weight: 600;
  }
  .title:first-child {
    margin-top: 0;
  }
  .value {
    justify-self: end;
    color: var(--color-text-primary);
    font-variant-numeric: tabular-nums;
  }
  .note {
    margin-left: 6px;
    color: var(--color-text-faint);
  }
  @container status-bar (max-width: 640px) {
    .words {
      display: none;
    }
    .icons {
      display: inline-flex;
    }
  }
</style>
