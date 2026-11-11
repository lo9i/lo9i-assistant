<script lang="ts">
  // The sign-in screens' frame: one glass card in the middle of the page, as the pairing page and an emailed link's
  // page show it.
  import type { Snippet } from "svelte";

  let { children }: { children: Snippet } = $props();
</script>

<main class="sign-in">
  <section class="card surface--glass">{@render children()}</section>
</main>

<style>
  .sign-in {
    display: grid;
    place-items: center;
    min-height: 100vh;
    padding: 16px;
    box-sizing: border-box;
    color: var(--color-text-primary);
  }
  .card {
    display: flex;
    flex-direction: column;
    gap: 16px;
    width: 100%;
    max-width: 400px;
    padding: 28px 24px;
    box-sizing: border-box;
  }
  .card :global(h1),
  .card :global(h2),
  .card :global(p) {
    margin: 0;
  }
  .card :global(form) {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .card :global(.buttons) {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
  }
</style>
