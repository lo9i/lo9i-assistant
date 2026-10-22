<script lang="ts">
  import type { Snippet } from "svelte";

  // A floating button in the window's bottom right corner (AppShell stacks them).
  let { label, tone = "", onclick, children }: { label: string; tone?: string; onclick: () => void; children: Snippet } = $props();
</script>

<button class="fab {tone}" aria-label={label} title={label} {onclick}>{@render children()}</button>

<style>
  .fab {
    display: grid;
    place-items: center;
    width: 29px;
    height: 29px;
    border: none;
    /* A speech bubble with its tail in the corner: talking with the assistant. */
    border-radius: 15px 15px 4px 15px;
    background: var(--color-action-primary);
    color: var(--color-action-on-primary);
    box-shadow: var(--shadow-popover);
    cursor: pointer;
    transition:
      transform 0.15s ease,
      filter 0.15s ease;
  }
  .fab:hover {
    filter: brightness(0.92);
    transform: translateY(-1px);
  }
  .fab.listening {
    background: var(--color-danger);
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
