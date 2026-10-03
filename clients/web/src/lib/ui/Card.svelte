<script lang="ts">
  import type { Snippet } from "svelte";

  type Props = { id?: string; title: string; sub?: string; status?: Snippet; children: Snippet };
  let { id, title, sub, status, children }: Props = $props();
</script>

<section {id} class="settings-card surface--glass">
  <header>
    <div>
      <h2 class="card-section-title">{title}</h2>
      {#if sub}<p class="card-section-sub">{sub}</p>{/if}
    </div>
    {#if status}{@render status()}{/if}
  </header>
  {@render children()}
</section>

<style>
  .settings-card {
    display: flex;
    flex-direction: column;
    gap: 24px;
    padding: 24px;
    scroll-margin-top: 92px;
  }
  header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 16px;
  }
  header div {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
</style>
