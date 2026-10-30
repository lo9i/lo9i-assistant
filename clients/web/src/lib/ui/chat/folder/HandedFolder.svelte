<script lang="ts">
  import FolderIcon from "@lucide/svelte/icons/folder";
  import PanelRightClose from "@lucide/svelte/icons/panel-right-close";
  import RefreshCw from "@lucide/svelte/icons/refresh-cw";
  import { untrack } from "svelte";
  import type { FilePreview, FolderChanges, Handoff } from "$lib/api/types";
  import { ChangeMarks } from "$lib/chat/folderChanges";
  import { FolderTree } from "$lib/chat/folderTree.svelte";
  import { Resource, useDaemon } from "$lib/daemon.svelte";
  import { t } from "$lib/i18n.svelte";
  import { describe } from "$lib/notices";
  import ChangedFiles from "./ChangedFiles.svelte";
  import FileText from "./FileText.svelte";
  import FolderLevel from "./FolderLevel.svelte";

  // Beside a conversation handed to an agent (/claude): the folder it works in, as a tree opened a folder at a time,
  // what git says changed there at the top, and a file's text when one is picked. It follows the agent's work: each
  // step it reports and its end (`agent_task_progress`, `agent_finished`) list the folder and its changes again, at
  // most once every REFRESH_MS, so a burst of steps reads it once.
  const REFRESH_MS = 1000;

  type Props = { threadId: string; handoff: Handoff; onclose: () => void };
  let { threadId, handoff, onclose }: Props = $props();
  const { client, hub } = useDaemon();

  // A new tree for another conversation or folder.
  const tree = $derived.by(() => {
    const thread = threadId;
    void handoff.folder;
    return new FolderTree((path) => client.conversations.agentFolder(thread, path));
  });
  const changes = new Resource<FolderChanges>(() => client.conversations.agentChanges(threadId));
  const marks = $derived(new ChangeMarks(changes.data?.changes ?? []));
  let picked = $state<string | null>(null);
  let preview = $state<FilePreview | null>(null);
  let previewError = $state("");
  let refreshing = $state(false);
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
    let timer: ReturnType<typeof setTimeout> | undefined;
    const soon = (data: Record<string, unknown>) => {
      if (data.thread_id !== thread || timer) return;
      timer = setTimeout(() => {
        timer = undefined;
        void refresh();
      }, REFRESH_MS);
    };
    const stop = hub.on(["agent_task_progress", "agent_finished"], soon);
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
    changes.reload();
    await Promise.all([tree.refresh(), picked ? read(picked) : Promise.resolve()]);
    refreshing = false;
  }

  function pick(path: string): void {
    picked = path;
    preview = null;
    previewError = "";
    void read(path);
  }

  async function read(path: string): Promise<void> {
    const call = ++reading;
    try {
      const found = await client.conversations.agentFile(threadId, path);
      if (call === reading) [preview, previewError] = [found, ""];
    } catch (e) {
      if (call === reading) [preview, previewError] = [null, describe(e)];
    }
  }

  function lastPart(path: string): string {
    return path.split("/").filter(Boolean).pop() ?? path;
  }
</script>

<aside class="panel surface--glass" class:previewing={picked !== null} aria-label={t("handedFolder.title")}>
  <header>
    <FolderIcon size={14} />
    <span class="folder" title={handoff.folder}>{lastPart(handoff.folder)}</span>
    <button
      class="btn btn--ghost btn--icon"
      class:spinning={refreshing}
      title={t("common.refresh")}
      aria-label={t("common.refresh")}
      onclick={() => void refresh()}><RefreshCw size={14} /></button
    >
    <button class="btn btn--ghost btn--icon" title={t("handedFolder.hide")} aria-label={t("handedFolder.hide")} onclick={onclose}
      ><PanelRightClose size={14} /></button
    >
  </header>
  {#if picked !== null}
    <FileText path={picked} {preview} error={previewError} onback={() => (picked = null)} />
  {:else}
    <ChangedFiles changes={changes.data} error={changes.error} {picked} onpick={pick} />
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
