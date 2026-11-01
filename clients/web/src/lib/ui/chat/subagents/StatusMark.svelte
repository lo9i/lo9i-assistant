<script lang="ts">
  import CircleCheck from "@lucide/svelte/icons/circle-check";
  import CircleStop from "@lucide/svelte/icons/circle-stop";
  import CircleX from "@lucide/svelte/icons/circle-x";
  import Hand from "@lucide/svelte/icons/hand";
  import LoaderCircle from "@lucide/svelte/icons/loader-circle";
  import type { BackgroundSubagent } from "$lib/api/types";

  // A background subagent's status as an icon in its colour: a spinner while it works, a raised hand while it waits
  // for the user. Its words go beside it.
  let { status }: { status: BackgroundSubagent["status"] } = $props();
</script>

<span class="mark mark--{status}" aria-hidden="true">
  {#if status === "running"}
    <LoaderCircle size={13} class="spin" />
  {:else if status === "waiting"}
    <Hand size={13} />
  {:else if status === "done"}
    <CircleCheck size={13} />
  {:else if status === "failed"}
    <CircleX size={13} />
  {:else}
    <CircleStop size={13} />
  {/if}
</span>

<style>
  .mark {
    display: inline-flex;
    flex: none;
    color: var(--color-text-faint);
  }
  .mark--running {
    color: var(--color-accent);
  }
  .mark--waiting {
    color: var(--color-warn);
  }
  .mark--done {
    color: var(--color-success);
  }
  .mark--failed {
    color: var(--color-danger);
  }
  .mark :global(.spin) {
    animation: spin 1s linear infinite;
  }
  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
  }
  @media (prefers-reduced-motion: reduce) {
    .mark :global(.spin) {
      animation: none;
    }
  }
</style>
