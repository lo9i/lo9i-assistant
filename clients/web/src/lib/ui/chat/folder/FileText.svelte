<script lang="ts">
  import ArrowLeft from "@lucide/svelte/icons/arrow-left";
  import Trash2 from "@lucide/svelte/icons/trash-2";
  import type { FilePreview } from "$lib/api/types";
  import { t } from "$lib/i18n.svelte";
  import { fileSize } from "$lib/logs";

  // A file of the folder in place of the tree: its text as the daemon sent it (never served as a page, so nothing in
  // it runs), its start for a big one, or a line saying it isn't text. Once it's read, it can be deleted
  // (`ondelete`, which asks first), when deleting is allowed.
  type Props = { path: string; preview: FilePreview | null; error: string; onback: () => void; ondelete?: (path: string) => void };
  let { path, preview, error, onback, ondelete }: Props = $props();
</script>

<section class="file" aria-label={path}>
  <header>
    <button class="btn btn--ghost btn--icon" title={t("handedFolder.back")} aria-label={t("handedFolder.back")} onclick={onback}
      ><ArrowLeft size={14} /></button
    >
    <span class="path" title={path}>{path}</span>
    {#if preview}<span class="text-caption">{fileSize(preview.size)}</span>{/if}
    {#if preview && ondelete}
      <button
        class="btn btn--ghost btn--icon delete"
        title={t("handedFolder.delete")}
        aria-label={t("handedFolder.delete")}
        onclick={() => ondelete?.(path)}><Trash2 size={14} /></button
      >
    {/if}
  </header>
  {#if error}
    <p class="note error-text">{error}</p>
  {:else if !preview}
    <p class="note text-caption">{t("common.loading")}</p>
  {:else if preview.text === null}
    <p class="note text-meta">{t("handedFolder.notPreviewable")}</p>
  {:else}
    {#if preview.truncated}<p class="note text-caption">{t("handedFolder.truncated", { size: fileSize(preview.size) })}</p>{/if}
    <pre>{preview.text}</pre>
  {/if}
</section>

<style>
  .file {
    display: flex;
    flex-direction: column;
    min-height: 0;
    flex: 1;
  }
  header {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 0 4px 6px;
  }
  .path {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-weight: 600;
  }
  pre {
    flex: 1;
    min-height: 0;
    margin: 0;
    padding: 10px 12px;
    overflow: auto;
    border-radius: var(--radius-sm);
    background: color-mix(in srgb, var(--color-text-primary) 4%, transparent);
    font-family: var(--font-mono);
    font-size: var(--font-size-xs);
    line-height: 1.5;
    tab-size: 4;
  }
  .note {
    margin: 0;
    padding: 4px 8px;
  }
  .delete:hover {
    color: var(--color-danger);
  }
</style>
