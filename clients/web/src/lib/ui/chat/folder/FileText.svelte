<script lang="ts">
  import ArrowLeft from "@lucide/svelte/icons/arrow-left";
  import Trash2 from "@lucide/svelte/icons/trash-2";
  import type { FileDiff, FilePreview } from "$lib/api/types";
  import { diffLines, type ChangeKind, type FileView } from "$lib/chat/folderChanges";
  import { t } from "$lib/i18n.svelte";
  import { fileSize } from "$lib/logs";

  // A file of the folder in place of the tree, as the daemon sent it (never served as a page, so nothing in it runs):
  // for a file git says changed, what changed (`git diff`), its lines coloured, with its whole text a click away while
  // it's still there; for any other, its text, its start for a big one, or a line saying it isn't text. Once it's
  // read, a file still there can be deleted (`ondelete`, which asks first) when deleting is allowed.
  type Props = {
    path: string;
    // What git says changed in it; null for a file it doesn't list (or the home folder's).
    change: ChangeKind | null;
    view: FileView;
    preview: FilePreview | null;
    diff: FileDiff | null;
    error: string;
    onview: (view: FileView) => void;
    onback: () => void;
    ondelete?: (path: string) => void;
  };
  let { path, change, view, preview, diff, error, onview, onback, ondelete }: Props = $props();
  const read = $derived(view === "diff" ? diff : preview);
  const there = $derived(change !== "deleted");
</script>

<section class="file" aria-label={path}>
  <header>
    <button class="btn btn--ghost btn--icon" title={t("handedFolder.back")} aria-label={t("handedFolder.back")} onclick={onback}
      ><ArrowLeft size={14} /></button
    >
    <span class="path" title={path}>{path}</span>
    {#if preview && view === "text"}<span class="text-caption">{fileSize(preview.size)}</span>{/if}
    {#if read && there && ondelete}
      <button
        class="btn btn--ghost btn--icon delete"
        title={t("handedFolder.delete")}
        aria-label={t("handedFolder.delete")}
        onclick={() => ondelete?.(path)}><Trash2 size={14} /></button
      >
    {/if}
  </header>
  {#if change && there}
    <div class="views" role="group" aria-label={t("handedFolder.view")}>
      <button
        class="btn btn--sm"
        class:btn--neutral={view === "diff"}
        class:btn--ghost={view !== "diff"}
        aria-pressed={view === "diff"}
        onclick={() => onview("diff")}>{t("handedFolder.changes")}</button
      >
      <button
        class="btn btn--sm"
        class:btn--neutral={view === "text"}
        class:btn--ghost={view !== "text"}
        aria-pressed={view === "text"}
        onclick={() => onview("text")}>{t("handedFolder.wholeFile")}</button
      >
    </div>
  {/if}
  {#if error}
    <p class="note error-text">{error}</p>
  {:else if !read}
    <p class="note text-caption">{t("common.loading")}</p>
  {:else if read.text === null}
    <p class="note text-meta">{t(view === "diff" ? "handedFolder.diffNotText" : "handedFolder.notPreviewable")}</p>
  {:else if view === "diff"}
    {#if read.truncated}<p class="note text-caption">{t("handedFolder.diffTruncated")}</p>{/if}
    <pre class="diff">{#each diffLines(read.text) as line, i (i)}<span class="line line--{line.kind}">{line.text || " "}</span>{/each}</pre>
  {:else}
    {#if read.truncated && preview}<p class="note text-caption">{t("handedFolder.truncated", { size: fileSize(preview.size) })}</p>{/if}
    <pre>{read.text}</pre>
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
  .views {
    display: flex;
    gap: 4px;
    padding: 0 4px 6px;
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
  /* A line each, wide as the longest, so a line's colour runs the whole width when it scrolls sideways. */
  .diff {
    display: grid;
    align-content: start;
    padding: 6px 0;
  }
  .line {
    padding: 0 12px;
    white-space: pre;
  }
  .line--added {
    background: color-mix(in srgb, var(--color-success) 14%, transparent);
  }
  .line--removed {
    background: color-mix(in srgb, var(--color-danger) 14%, transparent);
  }
  .line--hunk {
    color: var(--color-accent);
  }
  .line--meta {
    color: var(--color-text-faint);
  }
  .note {
    margin: 0;
    padding: 4px 8px;
  }
  .delete:hover {
    color: var(--color-danger);
  }
</style>
