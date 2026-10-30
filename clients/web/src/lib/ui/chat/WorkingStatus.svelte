<script lang="ts">
  import LoaderCircle from "@lucide/svelte/icons/loader-circle";
  import type { RunningTask } from "$lib/api/types";
  import { clock } from "$lib/clock.svelte";
  import { duration } from "$lib/duration";
  import { t } from "$lib/i18n.svelte";

  // In the status bar: the coding agents working in this conversation, and for how long; not the one it's handed
  // to, which shows by its name (AgentStatus). Their steps show in the thread.
  let { tasks }: { tasks: RunningTask[] } = $props();
  const time = clock();
</script>

{#each tasks as task (task.id)}
  <span class="working">
    <LoaderCircle size={13} class="spin" aria-hidden="true" />
    <span title="{task.agent} {t('chat.isWorking', { since: duration(task.started_at, time.now) })}"
      ><strong>{task.agent}</strong> {t("chat.isWorking", { since: duration(task.started_at, time.now) })}</span
    >
  </span>
{/each}

<style>
  /* Gives way after the conversation's figures when the status bar runs short. */
  .working {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    flex: 0 1 auto;
    min-width: 0;
  }
  .working > span {
    overflow: hidden;
    text-overflow: ellipsis;
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
