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
  /* The text takes the room the controls leave, so a long hint wraps beside them instead of pushing them under it. */
  .label {
    flex: 1 1 16rem;
    display: flex;
    flex-direction: column;
    gap: 2px;
    min-width: 0;
  }
  /* The controls stay together on one line at the right edge, so every row's last control lines up. */
  .control {
    flex: none;
    margin-left: auto;
    display: flex;
    align-items: center;
    gap: 8px;
  }
</style>
