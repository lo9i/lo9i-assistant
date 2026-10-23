<script lang="ts">
  import LoaderCircle from "@lucide/svelte/icons/loader-circle";
  import { duration } from "$lib/duration";
  import { resource } from "$lib/daemon.svelte";

  // In the status bar: the coding agents working in this conversation, and for how long. Their steps show in the
  // thread.
  let { threadId }: { threadId: string } = $props();

  const running = resource((c) => c.tasks.running(), ["agent_task_progress", "agent_task_reports", "background_ended"]);
  let now = $state(new Date().toISOString());
  $effect(() => {
    const timer = setInterval(() => (now = new Date().toISOString()), 30_000);
    return () => clearInterval(timer);
  });

  const here = $derived((running.data ?? []).filter((t) => t.thread_id === threadId));
</script>

{#each here as task (task.id)}
  <span class="working">
    <LoaderCircle size={13} class="spin" aria-hidden="true" />
    <span><strong>{task.agent}</strong> is working · {duration(task.started_at, now)}</span>
  </span>
{/each}

<style>
  .working {
    display: inline-flex;
    align-items: center;
    gap: 6px;
  }
  .working :global(.spin) {
    flex: none;
    animation: spin 1s linear infinite;
  }
  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
  }
  @media (prefers-reduced-motion: reduce) {
    .working :global(.spin) {
      animation: none;
    }
  }
</style>
