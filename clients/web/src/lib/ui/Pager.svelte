<script lang="ts">
  import ChevronLeft from "@lucide/svelte/icons/chevron-left";
  import ChevronRight from "@lucide/svelte/icons/chevron-right";
  import { pageCount } from "$lib/paging";

  /** `page` counts from 0. */
  let { page = $bindable(0), total, size }: { page?: number; total: number; size: number } = $props();
  const pages = $derived(pageCount(total, size));
  const current = $derived(Math.min(page, pages - 1));
</script>

<nav class="pager" aria-label="Pages">
  <span class="text-meta">{current * size + 1}–{Math.min((current + 1) * size, total)} of {total}</span>
  <button class="btn btn--ghost btn--sm" aria-label="Previous page" disabled={current === 0} onclick={() => (page = current - 1)}>
    <ChevronLeft size={16} />
  </button>
  <span class="text-label">{current + 1} / {pages}</span>
  <button class="btn btn--ghost btn--sm" aria-label="Next page" disabled={current >= pages - 1} onclick={() => (page = current + 1)}>
    <ChevronRight size={16} />
  </button>
</nav>

<style>
  .pager {
    display: flex;
    align-items: center;
    justify-content: flex-end;
    gap: 8px;
    padding: 12px 24px;
    border-top: 1px solid color-mix(in srgb, var(--color-border) 55%, transparent);
  }
  .text-meta {
    margin-right: 8px;
  }
</style>
