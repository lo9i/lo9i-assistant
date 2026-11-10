<script lang="ts">
  import type { Snippet } from "svelte";

  // One way of moving lo9i (over SSH, exporting, importing): a light panel in the Move card, its title and one short
  // line, then its form. Its fields lay out by the panel's width, not the window's, so the card's column decides.
  type Props = { title: string; caption: string; onsubmit: () => void; children: Snippet };
  let { title, caption, onsubmit, children }: Props = $props();
  const id = $props.id();
</script>

<form
  class="part"
  aria-labelledby={id}
  onsubmit={(e) => {
    e.preventDefault();
    onsubmit();
  }}
>
  <header>
    <h3 {id}>{title}</h3>
    <p class="text-caption">{caption}</p>
  </header>
  {@render children()}
</form>

<style>
  .part {
    display: flex;
    flex-direction: column;
    gap: 12px;
    min-width: 0;
    padding: 16px;
    border: 1px solid var(--surface-glass-border);
    border-radius: var(--radius-md);
    background: color-mix(in srgb, var(--color-text-primary) 2%, transparent);
    container-type: inline-size;
  }
  header {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }
  h3 {
    margin: 0;
    font-size: var(--font-size-sm);
    font-weight: 600;
  }
  p {
    margin: 0;
  }
  /* What the three forms share: their fields in a grid, and a last row with a checkbox and the button at its end. */
  .part :global(.fields) {
    display: grid;
    gap: 8px;
  }
  .part :global(.actions) {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 8px 12px;
  }
  .part :global(.actions .btn) {
    margin-left: auto;
  }
  .part :global(.check) {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: var(--font-size-sm);
    color: var(--color-text-muted);
    cursor: pointer;
  }
  .part :global(.text-meta) {
    margin: 0;
  }
</style>
