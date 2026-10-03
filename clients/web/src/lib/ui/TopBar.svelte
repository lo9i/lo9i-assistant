<script lang="ts">
  import type { Snippet } from "svelte";

  let { title, actions }: { title: string; actions?: Snippet } = $props();
  let scrolled = $state(false);
</script>

<svelte:window onscroll={() => (scrolled = window.scrollY > 4)} />

<header class="topbar" class:scrolled>
  <div class="inner">
    <h1>{title}</h1>
    {#if actions}<div class="actions">{@render actions()}</div>{/if}
  </div>
</header>

<style>
  .topbar {
    position: sticky;
    top: 0;
    z-index: 20;
  }
  .topbar::before {
    content: "";
    position: absolute;
    inset: 0 0 -36px;
    background: color-mix(in srgb, var(--color-bg-page) 30%, transparent);
    backdrop-filter: blur(18px);
    mask-image: linear-gradient(to bottom, #000 0 70%, transparent);
    opacity: 0;
    transition: opacity 0.2s ease;
    pointer-events: none;
  }
  .scrolled::before {
    opacity: 1;
  }
  .inner {
    position: relative;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    min-height: 76px;
    padding: 16px 16px 0;
    max-width: 1600px;
    margin: 0 auto;
  }
  h1 {
    min-width: 0;
    margin: 0;
    font-size: var(--font-size-xl);
    font-weight: 600;
    letter-spacing: -0.01em;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .actions {
    flex: none;
    display: flex;
    align-items: center;
    gap: 16px;
  }
  @media (max-width: 680px) {
    .inner {
      min-height: 60px;
    }
    h1 {
      font-size: var(--font-size-lg);
    }
  }
</style>
