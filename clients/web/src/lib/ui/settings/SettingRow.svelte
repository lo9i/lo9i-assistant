<script lang="ts">
  // One row of a settings card: what it is on the left, its controls on the right, wrapping under it when narrow.
  import type { Snippet } from "svelte";

  type Props = { label: string; hint?: Snippet; children: Snippet };
  let { label, hint, children }: Props = $props();
</script>

<div class="setting">
  <div class="label">
    <span class="text-label">{label}</span>
    {#if hint}<span class="text-caption">{@render hint()}</span>{/if}
  </div>
  <div class="control">{@render children()}</div>
</div>

<style>
  .setting {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    flex-wrap: wrap;
  }
  .label {
    display: flex;
    flex-direction: column;
    gap: 2px;
    min-width: 0;
  }
  .control {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }
</style>
