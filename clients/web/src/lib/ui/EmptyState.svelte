<script lang="ts">
  import type { Component } from "svelte";

  let { icon: Icon, title, text }: { icon: Component<{ size?: number }>; title: string; text: string } = $props();
</script>

<div class="empty">
  <span class="tile"><Icon size={20} /></span>
  <strong>{title}</strong>
  <p class="text-meta">{text}</p>
</div>

<style>
  .empty {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 8px;
    min-height: 180px;
    justify-content: center;
    padding: 40px 16px;
    text-align: center;
  }
  .tile {
    display: grid;
    place-items: center;
    width: 44px;
    height: 44px;
    border-radius: var(--radius-md);
    background: color-mix(in srgb, var(--color-accent) 18%, transparent);
    color: var(--color-accent);
  }
  p {
    margin: 0;
    max-width: 32ch;
  }
</style>
