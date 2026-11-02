<script lang="ts">
  import { t } from "$lib/i18n.svelte";

  // The side panel's and the Subagents page's filter: on, only those still working or waiting for the user show; off,
  // those that ended too.
  let { checked = $bindable(true) }: { checked?: boolean } = $props();
</script>

<label class="active-only text-meta" title={t("subagents.activeOnlyHint")}>
  <input type="checkbox" bind:checked />
  {t("subagents.activeOnly")}
</label>

<style>
  .active-only {
    display: flex;
    flex: none;
    align-items: center;
    gap: 6px;
    white-space: nowrap;
    cursor: pointer;
  }
</style>
