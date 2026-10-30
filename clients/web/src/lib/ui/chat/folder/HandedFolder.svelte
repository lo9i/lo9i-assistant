<script lang="ts">
  import FolderIcon from "@lucide/svelte/icons/folder";
  import PanelRightClose from "@lucide/svelte/icons/panel-right-close";
  import RefreshCw from "@lucide/svelte/icons/refresh-cw";
  import { untrack } from "svelte";
  import { DaemonUnavailableError } from "$lib/api/errors";
  import type { FileDiff, FilePreview, FolderChanges, Handoff } from "$lib/api/types";
  import { ChangeMarks, type ChangeKind, type FileView } from "$lib/chat/folderChanges";
  import { FolderTree, type Listing } from "$lib/chat/folderTree.svelte";
  import { resource, useDaemon } from "$lib/daemon.svelte";
  import { t } from "$lib/i18n.svelte";
  import { describe } from "$lib/notices";
  import Confirm from "$lib/ui/Confirm.svelte";
  import ChangedFiles from "./ChangedFiles.svelte";
  import FileText from "./FileText.svelte";
  import FolderLevel from "./FolderLevel.svelte";

  // Beside a conversation handed to an agent (/claude): the folder it works in, as a tree opened a folder at a time
  // (what git says was deleted shown where it was), what git says changed there at the top, and a file when one is
  // picked: what changed in it when git lists it, its text otherwise. It follows the agent's work: each
  // step it reports and its end (`agent_task_progress`, `agent_finished`) list the folder and its changes again, at
  // most once every REFRESH_MS, so a burst of steps reads it once, in one request (agentRefresh) that asks git once. Beside any other conversation (no `handoff`): the
  // user's home folder, the same way but without changes, read again only when asked. A file shown can be deleted,
  // to the system's trash, once the user confirms, while Settings → General allows it (off until turned on).
  const REFRESH_MS = 1000;

  type Props = { threadId: string; handoff: Handoff | null; onclose: () => void };
  let { threadId, handoff, onclose }: Props = $props();
  const { client, hub, notices } = useDaemon();

  // A new tree for another conversation or folder.
  const tree = $derived.by(() => {
    const thread = threadId;
    if (handoff === null) return new FolderTree((path) => client.folders.home(path));
    void handoff.folder;
    return new FolderTree((path) => client.conversations.agentFolder(thread, path));
  });
  const deletable = resource((c) => c.folders.deleting(), ["settings"]);
  // What git says changed, read with the folders; the error, when reading them failed (not for a daemon away, which
  // the app says everywhere).
  let changes = $state<FolderChanges>();
  let changesError = $state<string | null>(null);
  const marks = $derived(new ChangeMarks((handoff && changes?.changes) || []));
  const hideLabel = $derived(handoff ? t("handedFolder.hide") : t("handedFolder.hideHome"));
  let picked = $state<string | null>(null);
  // What git says changed in the file picked: it opens on what changed, its text a click away.
  const pickedChange = $derived(picked === null ? null : fileChange(picked));
  let view = $state<FileView>("text");
  let preview = $state<FilePreview | null>(null);
  let diff = $state<FileDiff | null>(null);
  let previewError = $state("");
  let refreshing = $state(false);
  // The file the user asked to delete, until they confirm or cancel.
  let deleting = $state<string | null>(null);
  let reading = 0;

  $effect(() => {
    void tree;
    untrack(() => {
      picked = null;
      void refresh();
    });
  });

  $effect(() => {
    const thread = threadId;
    const handed = handoff !== null;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const soon = (data: Record<string, unknown>) => {
      if (data.thread_id !== thread || timer) return;
      timer = setTimeout(() => {
        timer = undefined;
        void refresh();
      }, REFRESH_MS);
    };
    const stop = handed ? hub.on(["agent_task_progress", "agent_finished"], soon) : () => {};
    const stopReconnect = hub.onReconnect(() => void refresh());
    return () => {
      stop();
      stopReconnect();
      clearTimeout(timer);
    };
  });

  /** The folder, its changes and the file shown, read again. */
  async function refresh(): Promise<void> {
    refreshing = true;
    await Promise.all([tree.refresh(handoff ? readHanded : undefined), picked ? read(picked) : Promise.resolve()]);
    refreshing = false;
  }

  /** The handed folder's open folders and its changes, together. */
  async function readHanded(paths: string[]): Promise<Record<string, Listing>> {
    try {
      const found = await client.conversations.agentRefresh(threadId, paths);
      [changes, changesError] = [found.changes, null];
      return Object.fromEntries(found.folders.map((f) => [f.path, f.contents ? { contents: f.contents } : { error: f.error }]));
    } catch (e) {
      if (!(e instanceof DaemonUnavailableError)) changesError = describe(e);
      throw e;
    }
  }

  function pick(path: string): void {
    picked = path;
    view = fileChange(path) ? "diff" : "text";
    [preview, diff, previewError] = [null, null, ""];
    void read(path);
  }

  function show(shown: FileView): void {
    view = shown;
    previewError = "";
    if (picked !== null) void read(picked);
  }

  /** The file picked, as it's shown: what changed in it, or its text. */
  async function read(path: string): Promise<void> {
    const call = ++reading;
    const shown = view;
    try {
      if (shown === "diff") {
        const found = await client.conversations.agentDiff(threadId, path);
        if (call === reading) [diff, previewError] = [found, ""];
      } else {
        const found = handoff ? await client.conversations.agentFile(threadId, path) : await client.folders.homeFile(path);
        if (call === reading) [preview, previewError] = [found, ""];
      }
    } catch (e) {
      if (call === reading) previewError = describe(e);
    }
  }

  function fileChange(path: string): ChangeKind | null {
    const mark = marks.of(path, false);
    return mark === null || mark === "inside" ? null : mark;
  }

  /** Deletes the file once the user confirms, then shows the tree without it. */
  async function remove(path: string): Promise<void> {
    deleting = null;
    try {
      await (handoff ? client.conversations.deleteAgentFile(threadId, path) : client.folders.deleteHomeFile(path));
    } catch (e) {
      notices.report(e);
      return;
    }
    if (picked === path) picked = null;
    void refresh();
  }

  function lastPart(path: string): string {
    return path.split("/").filter(Boolean).pop() ?? path;
  }
</script>

<aside class="panel surface--glass" class:previewing={picked !== null} aria-label={t("handedFolder.title")}>
  <header>
    <FolderIcon size={14} />
    {#if handoff}
      <span class="folder" title={handoff.folder}>{lastPart(handoff.folder)}</span>
    {:else}
      <span class="folder" title="~">{t("handedFolder.home")}</span>
    {/if}
    <button
      class="btn btn--ghost btn--icon"
      class:spinning={refreshing}
      title={t("common.refresh")}
      aria-label={t("common.refresh")}
      onclick={() => void refresh()}><RefreshCw size={14} /></button
    >
    <button class="btn btn--ghost btn--icon" title={hideLabel} aria-label={hideLabel} onclick={onclose}
      ><PanelRightClose size={14} /></button
    >
  </header>
  {#if picked !== null}
    <FileText
      path={picked}
      change={pickedChange}
      {view}
      {preview}
      {diff}
      error={previewError}
      onview={show}
      onback={() => (picked = null)}
      ondelete={deletable.data ? (path) => (deleting = path) : undefined}
    />
  {:else}
    {#if handoff}<ChangedFiles {changes} error={changesError} {picked} onpick={pick} />{/if}
    <div class="tree">
      <FolderLevel
        path=""
        listings={tree.listings}
        opened={tree.opened}
        {marks}
        {picked}
        ontoggle={(path) => void tree.toggle(path)}
        onpick={pick}
      />
    </div>
  {/if}
</aside>

{#if deleting !== null}
  {@const path = deleting}
  <Confirm
    title={t("handedFolder.deleteTitle", { name: lastPart(path) })}
    text={t("handedFolder.deleteText", { path })}
    action={t("handedFolder.deleteAction")}
    onanswer={(yes) => (yes ? void remove(path) : (deleting = null))}
  />
{/if}

<style>
  .panel {
    display: flex;
    flex-direction: column;
    gap: 8px;
    width: 300px;
    flex: none;
    min-height: 0;
    height: 100%;
    padding: 10px 8px;
    transition: width 0.15s ease;
  }
  /* A file's text needs more room than its name. */
  .panel.previewing {
    width: min(50%, 720px);
  }
  header {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 0 0 0 8px;
    color: var(--color-text-muted);
  }
  .folder {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-weight: 600;
    color: var(--color-text-primary);
  }
  .tree {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    border-top: 1px solid color-mix(in srgb, var(--color-border) 55%, transparent);
    padding-top: 6px;
  }
  .spinning :global(svg) {
    animation: spin 0.8s linear infinite;
  }
  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
  }
  @media (prefers-reduced-motion: reduce) {
    .spinning :global(svg) {
      animation: none;
    }
  }
  /* Narrow, it covers the chat from the right instead of taking room beside it. */
  @media (max-width: 900px) {
    .panel,
    .panel.previewing {
      position: absolute;
      top: 0;
      right: 0;
      bottom: 0;
      z-index: var(--z-popover);
      width: min(100%, 420px);
      background: var(--surface-modal-bg);
      box-shadow: var(--shadow-popover);
    }
  }
</style>
