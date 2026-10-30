<script lang="ts">
  import Coins from "@lucide/svelte/icons/coins";
  import Mail from "@lucide/svelte/icons/mail";
  import Wrench from "@lucide/svelte/icons/wrench";
  import { statsDetail, statsFigures, statsLine } from "$lib/conversationStats";
  import { resource } from "$lib/daemon.svelte";

  // In the status bar: how long the conversation is and what it took, with the figures in its tooltip; where the bar
  // has little room (StatusBar's container), icons stand for the words. Loaded again
  // when the conversation changes and when a reply ends; shown from the start (all zeros), hidden only when it can't be loaded.
  let { threadId }: { threadId: string } = $props();

  const stats = resource((c) => c.conversations.stats(threadId), ["run_finished"]);
  let now = $state(new Date().toISOString());
  $effect(() => {
    const timer = setInterval(() => (now = new Date().toISOString()), 60_000);
    return () => clearInterval(timer);
  });

  // The last conversation's stats stay until this one's arrive; they aren't shown meanwhile.
  const shown = $derived(stats.data && !stats.error && stats.data.thread_id === threadId ? stats.data : null);
</script>

{#if shown}
  {@const figures = statsFigures(shown, now)}
  <span class="stats" title={statsDetail(shown)}>
    <span class="words">{statsLine(shown, now)}</span>
    <span class="icons" aria-label={statsLine(shown, now)}>
      <span><Mail size={12} aria-hidden="true" />{figures.messages}</span>
      <span><Coins size={12} aria-hidden="true" />{figures.tokens}</span>
      <span><Wrench size={12} aria-hidden="true" />{figures.tools}</span>
      {#if figures.ago}<span>{figures.ago}</span>{/if}
    </span>
  </span>
{/if}

<style>
  /* The first to give way when the status bar runs short; the tooltip has it all. */
  .stats {
    flex: 0 100 auto;
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
  @container status-bar (max-width: 640px) {
    .words {
      display: none;
    }
    .icons {
      display: inline-flex;
    }
  }
</style>
