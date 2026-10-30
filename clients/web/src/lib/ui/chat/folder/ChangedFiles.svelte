<script lang="ts">
  import ChevronRight from "@lucide/svelte/icons/chevron-right";
  import type { FolderChanges } from "$lib/api/types";
  import { t } from "$lib/i18n.svelte";
  import ChangeMark from "./ChangeMark.svelte";

  // The top of the side panel: what git says changed in the handed folder, each file opening its preview (not a
  // deleted one, nor an untracked folder, which git lists once for everything in it). Folded away with its heading.
  // `error` says why they couldn't be read: in place of Loading the first time, above the ones read before after.
  type Props = {
    changes: FolderChanges | undefined;
    error?: string | null;
    picked: string | null;
    onpick: (path: string) => void;
  };
  let { changes, error = null, picked, onpick }: Props = $props();
  let folded = $state(false);
</script>

<section class="changed" aria-label={t("handedFolder.changed")}>
  <button class="heading" aria-expanded={!folded} onclick={() => (folded = !folded)}>
    <span class="chevron" class:open={!folded}><ChevronRight size={12} /></span>
    <span class="micro-label">{t("handedFolder.changed")}</span>
    {#if changes?.changes.length}<span class="pill">{changes.changes.length}{changes.truncated ? "+" : ""}</span>{/if}
  </button>
  {#if !folded}
    {#if error}<p class="note error-text">{error}</p>{/if}
    {#if !changes}
      {#if !error}<p class="note text-caption">{t("common.loading")}</p>{/if}
    {:else if !changes.repository}
      <p class="note text-caption">{t("handedFolder.notRepository")}</p>
    {:else if !changes.changes.length}
      <p class="note text-caption">{t("handedFolder.noChanges")}</p>
    {:else}
      <ul>
        {#each changes.changes as change (`${change.status}:${change.path}`)}
          {@const openable = change.status !== "deleted" && !change.path.endsWith("/")}
          <li>
            <button
              class="row"
              class:picked={change.path === picked}
              class:gone={change.status === "deleted"}
              title={change.path}
              disabled={!openable}
              onclick={() => onpick(change.path)}
            >
              <span class="path">{change.path}</span>
              <ChangeMark mark={change.status} />
            </button>
          </li>
        {/each}
      </ul>
      {#if changes.truncated}<p class="note text-caption">{t("handedFolder.moreChanges")}</p>{/if}
    {/if}
  {/if}
</section>

<style>
  .changed {
    display: flex;
    flex-direction: column;
    min-height: 0;
  }
  .heading {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 4px 8px;
    border: 0;
    background: none;
    color: inherit;
    cursor: pointer;
  }
  .chevron {
    display: inline-flex;
    color: var(--color-text-faint);
    transition: transform 0.12s ease;
  }
  .chevron.open {
    transform: rotate(90deg);
  }
  ul {
    list-style: none;
    margin: 0;
    padding: 0;
    max-height: 30vh;
    overflow-y: auto;
  }
  .row {
    display: flex;
    align-items: center;
    gap: 8px;
    width: 100%;
    padding: 3px 8px 3px 26px;
    border: 0;
    border-radius: var(--radius-sm);
    background: none;
    color: var(--color-text-muted);
    font: inherit;
    font-size: var(--font-size-sm);
    text-align: left;
    cursor: pointer;
  }
  .row:hover:not(:disabled) {
    background: var(--color-bg-hover-ghost);
    color: var(--color-text-primary);
  }
  .row:disabled {
    cursor: default;
  }
  .row.picked {
    background: color-mix(in srgb, var(--color-text-primary) 8%, transparent);
    color: var(--color-text-primary);
  }
  .row.gone .path {
    text-decoration: line-through;
  }
  .path {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .note {
    margin: 0;
    padding: 3px 8px 3px 26px;
  }
</style>
