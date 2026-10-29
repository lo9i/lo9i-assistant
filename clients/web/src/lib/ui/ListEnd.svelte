<script lang="ts" generics="T">
  import { t } from "$lib/i18n.svelte";
  import type { PagedList } from "$lib/pagedList.svelte";

  // After a paged list's last item: in sight, it loads the next page, and says so while it does.
  let { list }: { list: PagedList<T> } = $props();
  let end = $state<HTMLElement>();

  $effect(() => {
    if (!end) return;
    // A little before it's in sight, so the next page is usually there by the time it's reached.
    const observer = new IntersectionObserver(([entry]) => list.seen(entry.isIntersecting), { rootMargin: "200px" });
    observer.observe(end);
    return () => {
      observer.disconnect();
      list.seen(false);
    };
  });
</script>

{#if list.error}
  <p class="end error-text">
    {list.error}
    <button class="btn btn--ghost btn--sm" onclick={() => list.reload()}>{t("app.tryAgain")}</button>
  </p>
{:else if !list.done}
  <p class="end text-meta" bind:this={end}>{list.loading ? t("common.loadingMore") : ""}</p>
{/if}

<style>
  .end {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    margin: 0;
    padding: 12px 24px;
    min-height: 44px;
  }
</style>
