<script lang="ts">
  import { statsDetail, statsLine } from "$lib/conversationStats";
  import { resource } from "$lib/daemon.svelte";

  // In the status bar: how long the conversation is and what it took, with the figures in its tooltip. Loaded again
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
  <span class="stats" title={statsDetail(shown)}>{statsLine(shown, now)}</span>
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
</style>
