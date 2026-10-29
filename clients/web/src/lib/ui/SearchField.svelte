<script lang="ts">
  import Search from "@lucide/svelte/icons/search";
  import { t } from "$lib/i18n.svelte";

  /** `label` names what is searched, for screen readers ("Search jobs"). */
  let { value = $bindable(""), label }: { value?: string; label: string } = $props();
</script>

<label class="search">
  <Search size={16} />
  <input placeholder={t("common.search")} aria-label={label} bind:value />
</label>

<style>
  .search {
    display: flex;
    align-items: center;
    gap: 8px;
    flex: 0 1 280px;
    padding: 0 16px;
    border: 1px solid var(--color-border);
    border-radius: var(--radius-sm);
    background: color-mix(in srgb, var(--color-bg-card-hover) 76%, transparent);
    color: var(--color-text-faint);
  }
  .search:focus-within {
    border-color: var(--color-accent);
  }
  input {
    flex: 1;
    min-width: 0;
    border: 0;
    outline: none;
    background: none;
    padding: 8px 0;
    color: var(--color-text-primary);
  }
</style>
