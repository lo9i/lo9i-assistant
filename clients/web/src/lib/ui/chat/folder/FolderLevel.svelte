<script lang="ts">
  import ChevronRight from "@lucide/svelte/icons/chevron-right";
  import FileIcon from "@lucide/svelte/icons/file";
  import Folder from "@lucide/svelte/icons/folder";
  import FolderOpen from "@lucide/svelte/icons/folder-open";
  import type { ChangeMarks } from "$lib/chat/folderChanges";
  import type { Listing } from "$lib/chat/folderTree.svelte";
  import { t } from "$lib/i18n.svelte";
  import ChangeMark from "./ChangeMark.svelte";
  import Self from "./FolderLevel.svelte";

  // One folder of the handed folder's tree, and the folders open inside it, each a level deeper. A folder opens on a
  // click, listed the first time; a file opens its preview.
  type Props = {
    path: string;
    listings: Record<string, Listing>;
    opened: Record<string, boolean>;
    marks: ChangeMarks;
    picked: string | null;
    ontoggle: (path: string) => void;
    onpick: (path: string) => void;
    depth?: number;
  };
  let { path, listings, opened, marks, picked, ontoggle, onpick, depth = 0 }: Props = $props();
  const listing = $derived(listings[path]);
</script>

{#if !listing}
  <p class="note text-caption" style:--depth={depth}>{t("common.loading")}</p>
{:else if "error" in listing}
  <p class="note error-text" style:--depth={depth}>{listing.error}</p>
{:else if !listing.contents.entries.length}
  <p class="note text-caption" style:--depth={depth}>{t("handedFolder.empty")}</p>
{:else}
  <ul role={depth ? "group" : "tree"} aria-label={depth ? undefined : t("handedFolder.title")}>
    {#each listing.contents.entries as entry (entry.path)}
      {@const mark = marks.of(entry.path, entry.folder)}
      {@const open = !!opened[entry.path]}
      <li role="treeitem" aria-expanded={entry.folder ? open : undefined} aria-selected={entry.path === picked}>
        <button
          class="row"
          class:picked={entry.path === picked}
          style:--depth={depth}
          title={entry.path}
          onclick={() => (entry.folder ? ontoggle(entry.path) : onpick(entry.path))}
        >
          {#if entry.folder}
            <span class="chevron" class:open><ChevronRight size={12} /></span>
            {#if open}<FolderOpen size={14} />{:else}<Folder size={14} />{/if}
          {:else}
            <span class="chevron"></span><FileIcon size={14} />
          {/if}
          <span class="name">{entry.name}</span>
          {#if mark}<ChangeMark {mark} />{/if}
        </button>
        {#if entry.folder && open}
          <Self path={entry.path} {listings} {opened} {marks} {picked} {ontoggle} {onpick} depth={depth + 1} />
        {/if}
      </li>
    {/each}
  </ul>
  {#if listing.contents.truncated}<p class="note text-caption" style:--depth={depth}>{t("handedFolder.moreEntries")}</p>{/if}
{/if}

<style>
  ul {
    list-style: none;
    margin: 0;
    padding: 0;
  }
  .row {
    display: flex;
    align-items: center;
    gap: 6px;
    width: 100%;
    padding: 3px 8px 3px calc(8px + var(--depth) * 14px);
    border: 0;
    border-radius: var(--radius-sm);
    background: none;
    color: var(--color-text-muted);
    font: inherit;
    font-size: var(--font-size-sm);
    text-align: left;
    cursor: pointer;
  }
  .row:hover {
    background: var(--color-bg-hover-ghost);
    color: var(--color-text-primary);
  }
  .row.picked {
    background: color-mix(in srgb, var(--color-text-primary) 8%, transparent);
    color: var(--color-text-primary);
    box-shadow: inset 3px 0 0 var(--color-accent);
  }
  .chevron {
    display: inline-flex;
    flex: none;
    width: 12px;
    transition: transform 0.12s ease;
  }
  .chevron.open {
    transform: rotate(90deg);
  }
  .name {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .note {
    margin: 0;
    padding: 3px 8px 3px calc(26px + var(--depth) * 14px);
  }
</style>
