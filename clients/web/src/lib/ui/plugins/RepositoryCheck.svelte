<script lang="ts">
  import { ago } from "$lib/duration";
  import type { CheckState } from "$lib/pluginUpdates";

  // Beside the Plugins toolbar: the list shown is the one kept from the last check, while the repositories are
  // checked again in the background. Quiet either way: a check that fails leaves that list.
  let { check, checked }: { check: CheckState; checked: string } = $props();

  let now = $state(new Date().toISOString());
  $effect(() => {
    const timer = setInterval(() => (now = new Date().toISOString()), 60_000);
    return () => clearInterval(timer);
  });
</script>

{#if check === "checking"}
  <span class="text-caption check"><span class="spinner"></span>Checking for updates…</span>
{:else if check === "failed"}
  <span class="text-caption check" title="The repositories couldn't be reached; this is the list from the last check."
    >Couldn't check for updates{checked ? ` · checked ${ago(checked, now)}` : ""}</span
  >
{:else if checked}
  <span class="text-caption check" title={new Date(checked).toLocaleString()}>Checked {ago(checked, now)}</span>
{/if}

<style>
  .check {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    white-space: nowrap;
    color: var(--color-text-muted);
  }
  .spinner {
    width: 10px;
    height: 10px;
    border-width: 1.5px;
  }
</style>
