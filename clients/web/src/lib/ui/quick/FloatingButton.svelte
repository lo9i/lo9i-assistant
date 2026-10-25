<script lang="ts">
  import type { Snippet } from "svelte";

  // A quick button in the sidebar's bottom bar.
  let { label, tone = "", onclick, children }: { label: string; tone?: string; onclick: () => void; children: Snippet } = $props();
</script>

<button class="bar-item fab {tone}" aria-label={label} title={label} {onclick}>{@render children()}</button>

<style>
  .fab.listening {
    background: var(--color-danger);
    color: #fff;
    animation: pulse 1.4s ease-in-out infinite;
  }
  .fab :global(.spin) {
    animation: spin 1s linear infinite;
  }
  @keyframes pulse {
    50% {
      box-shadow: 0 0 0 6px color-mix(in srgb, var(--color-danger) 20%, transparent);
    }
  }
  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
  }
</style>
