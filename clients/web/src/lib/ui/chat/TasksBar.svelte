<script lang="ts">
  import LoaderCircle from "@lucide/svelte/icons/loader-circle";
  import type { RunningTask } from "$lib/api/types";
  import { duration } from "$lib/duration";
  import { resource } from "$lib/daemon.svelte";
  import Modal from "../Modal.svelte";

  // Coding agents' tasks running in the background, each with what it's doing now. A task from another
  // conversation says which, and opens it. One working in this conversation is in the status bar
  // (WorkingStatus), its steps in the thread.
  let { threadId, onopen }: { threadId: string; onopen: (threadId: string) => void } = $props();

  const running = resource((c) => c.tasks.running(), ["agent_task_progress", "agent_task_reports", "background_ended"]);
  const conversations = resource((c) => c.conversations.list(), ["conversations"]);
  let shown = $state<string | null>(null);
  let now = $state(new Date().toISOString());
  $effect(() => {
    const timer = setInterval(() => (now = new Date().toISOString()), 30_000);
    return () => clearInterval(timer);
  });

  const tasks = $derived((running.data ?? []).filter((t) => t.thread_id !== threadId));
  const open = $derived(tasks.find((t) => t.id === shown));

  function elsewhere(task: RunningTask): string | null {
    if (!task.thread_id || task.thread_id === threadId) return null;
    return conversations.data?.find((c) => c.thread_id === task.thread_id)?.title || "another conversation";
  }
</script>

{#each tasks as task (task.id)}
  {@const other = elsewhere(task)}
  <div class="task" role="status">
    <LoaderCircle size={14} class="spin" aria-hidden="true" />
    <span>
      <strong>{task.agent}</strong> is working · {duration(task.started_at, now)}{#if other}&nbsp;· in {other}{/if}
      {#if task.steps.length}<span class="last">{task.steps.at(-1)}</span>{/if}
    </span>
    <button type="button" class="btn btn--ghost btn--sm" onclick={() => (shown = task.id)}>Steps</button>
    {#if other}
      <button type="button" class="btn btn--ghost btn--sm" onclick={() => onopen(task.thread_id)}>Open</button>
    {/if}
  </div>
{/each}

{#if open}
  <Modal title="{open.agent} · task {open.id}" description={open.asked} onclose={() => (shown = null)}>
    {#if open.steps.length}
      <ol class="steps">
        {#each open.steps as step, i (i)}<li>{step}</li>{/each}
      </ol>
    {:else}
      <p class="text-meta">No steps yet.</p>
    {/if}
  </Modal>
{/if}

<style>
  .task {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 8px;
    padding: 4px 16px;
    color: var(--color-text-muted);
    font-size: var(--font-size-sm);
  }
  .task > span {
    flex: 1;
    min-width: 0;
    overflow-wrap: anywhere;
  }
  .last {
    display: block;
    font-family: var(--font-mono);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .task :global(.spin) {
    flex: none;
    animation: spin 1s linear infinite;
  }
  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
  }
  @media (prefers-reduced-motion: reduce) {
    .task :global(.spin) {
      animation: none;
    }
  }
  .steps {
    margin: 0;
    padding-left: 24px;
    max-height: 60dvh;
    overflow-y: auto;
    font-family: var(--font-mono);
    font-size: var(--font-size-sm);
    overflow-wrap: anywhere;
  }
</style>
