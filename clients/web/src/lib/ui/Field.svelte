<script lang="ts">
  import type { Snippet } from "svelte";

  // A form field with its label above it, so it stays named once it's filled in (a placeholder goes away).
  let { label, children }: { label: string; children: Snippet } = $props();
</script>

<label class="field">
  <span class="field-label">{label}</span>
  {@render children()}
</label>

<style>
  .field {
    display: flex;
    flex-direction: column;
    align-items: stretch;
    gap: 6px;
  }
  .field-label {
    font-size: var(--font-size-sm);
    font-weight: 600;
  }
</style>
